"""实验室混样批次追溯 API。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db
from .core import raw_composition


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # 启动时初始化数据库（建表，幂等）
    yield


app = FastAPI(title="Lab Mixture Traceability API", lifespan=lifespan)


# ---------- 请求 / 响应模型 ----------

class RawSampleCreate(BaseModel):
    name: str = ""


class RecipeItem(BaseModel):
    batch_id: int
    portions: int = Field(gt=0, description="投入份数，必须为正整数")


class MixCreate(BaseModel):
    name: str = ""
    recipe: list[RecipeItem] = Field(min_length=1, description="配方，至少一个原料批次")


class BatchOut(BaseModel):
    batch_id: int
    kind: str
    name: str


class RecipeItemOut(BaseModel):
    batch_id: int
    portions: int


class BatchDetailOut(BatchOut):
    recipe: list[RecipeItemOut] | None = None


class CompositionEntry(BaseModel):
    raw_sample_id: int
    numerator: int
    denominator: int


class CompositionOut(BaseModel):
    batch_id: int
    kind: str
    composition: list[CompositionEntry]


# ---------- 接口 ----------

@app.post("/raw-samples", response_model=BatchOut, status_code=201)
def create_raw_sample(body: RawSampleCreate):
    """登记一个原始样本批次。"""
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO batches (kind, name) VALUES ('raw', ?)", (body.name,)
        )
        return BatchOut(batch_id=cur.lastrowid, kind="raw", name=body.name)


@app.post("/mixes", response_model=BatchOut, status_code=201)
def create_mix(body: MixCreate):
    """按配方创建混样批次。

    - 空配方、非正份数由请求模型校验（422）；
    - 引用不存在的批次返回 400；
    - 配方中重复引用同一批次时，份数合并累加。
    """
    merged: dict[int, int] = {}
    for item in body.recipe:
        merged[item.batch_id] = merged.get(item.batch_id, 0) + item.portions

    with db.connect() as conn:
        known = {
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM batches WHERE id IN ({','.join('?' * len(merged))})",
                tuple(merged),
            )
        }
        unknown = sorted(set(merged) - known)
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"unknown batch id(s): {unknown}"
            )

        cur = conn.execute(
            "INSERT INTO batches (kind, name) VALUES ('mix', ?)", (body.name,)
        )
        mix_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO recipe_items (mix_id, ingredient_id, portions) VALUES (?, ?, ?)",
            [(mix_id, ingredient_id, portions) for ingredient_id, portions in merged.items()],
        )
        return BatchOut(batch_id=mix_id, kind="mix", name=body.name)


@app.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: int):
    """查询批次基本信息（混样批次含配方）。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, kind, name FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="batch not found")
        recipe = None
        if row["kind"] == "mix":
            recipe = [
                RecipeItemOut(batch_id=r["ingredient_id"], portions=r["portions"])
                for r in conn.execute(
                    "SELECT ingredient_id, portions FROM recipe_items "
                    "WHERE mix_id = ? ORDER BY ingredient_id",
                    (batch_id,),
                )
            ]
        return BatchDetailOut(
            batch_id=row["id"], kind=row["kind"], name=row["name"], recipe=recipe
        )


@app.get("/batches/{batch_id}/composition", response_model=CompositionOut)
def get_composition(batch_id: int):
    """递归计算任一批次的原始样本占比，以约分后的分子/分母返回。"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT kind FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="batch not found")
        composition = raw_composition(batch_id, conn)
        return CompositionOut(
            batch_id=batch_id,
            kind=row["kind"],
            composition=[
                CompositionEntry(
                    raw_sample_id=raw_id,
                    numerator=frac.numerator,
                    denominator=frac.denominator,
                )
                for raw_id, frac in sorted(composition.items())
            ],
        )
