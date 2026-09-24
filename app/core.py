"""按配方递归计算混样批次中各原始样本的精确占比。

使用 fractions.Fraction 做有理数运算：同一原始样本经多条路径
进入混样时占比直接相加合并，Fraction 自动约分，全程无浮点误差。
"""
from fractions import Fraction


def raw_composition(batch_id: int, conn, memo: dict | None = None) -> dict[int, Fraction]:
    """返回 {原始样本批次 id: 占比}，所有占比之和恒等于 1。

    由于新批次只能引用已创建的批次，引用图必然是无环的，
    递归必然终止；memo 避免重复子图的重复计算。
    """
    if memo is None:
        memo = {}
    if batch_id in memo:
        return memo[batch_id]

    row = conn.execute("SELECT kind FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise KeyError(batch_id)

    if row["kind"] == "raw":
        result = {batch_id: Fraction(1, 1)}
    else:
        items = conn.execute(
            "SELECT ingredient_id, portions FROM recipe_items WHERE mix_id = ?",
            (batch_id,),
        ).fetchall()
        total = sum(item["portions"] for item in items)
        result = {}
        for item in items:
            weight = Fraction(item["portions"], total)
            for raw_id, frac in raw_composition(item["ingredient_id"], conn, memo).items():
                result[raw_id] = result.get(raw_id, Fraction(0)) + weight * frac

    memo[batch_id] = result
    return result
