# 实验室混样批次追溯 API

基于 FastAPI + SQLite 的混样批次追溯服务：登记原始样本、按配方创建混样批次，
并对任一批次递归计算各原始样本的精确占比（约分后的分子/分母，无浮点误差）。

## 快速启动

只需一条命令（依赖安装与数据库建表均在启动时自动完成）：

```bash
docker compose up --build
```

启动后访问：

- API 地址：http://localhost:8000
- 交互式文档（Swagger UI）：http://localhost:8000/docs

## 配置

| 环境变量  | 默认值          | 说明                     |
|-----------|-----------------|--------------------------|
| `DB_PATH` | `/data/lab.db`  | SQLite 数据库文件路径    |

Compose 已将 `/data` 挂载为命名卷 `lab-data`，容器重启数据不丢失。
端口映射为 `8000:8000`，如需修改请编辑 `docker-compose.yml` 的 `ports`。

## 接口

| 方法 | 路径                            | 说明                           |
|------|---------------------------------|--------------------------------|
| POST | `/raw-samples`                  | 登记原始样本批次               |
| POST | `/mixes`                        | 按配方创建混样批次             |
| GET  | `/batches/{id}`                 | 查询批次信息（混样含配方）     |
| GET  | `/batches/{id}/composition`     | 递归计算原始样本占比           |

校验规则：

- 空配方（`recipe` 为空数组）→ 422
- 投入份数非正整数（`portions <= 0`）→ 422
- 引用不存在的批次 → 400
- 新批次只能引用已创建的批次，因此配方图天然无环
- 配方中重复引用同一批次时，份数自动合并累加

占比计算：按每层投入份数加权递归展开，同一原始样本经多条路径进入时占比合并，
结果以 `fractions.Fraction` 精确表示并自动约分，所有占比之和恒等于 1。

## 示例请求

```bash
# 1. 登记两个原始样本
curl -s -X POST localhost:8000/raw-samples -H 'Content-Type: application/json' \
  -d '{"name": "sample-A"}'
# {"batch_id":1,"kind":"raw","name":"sample-A"}

curl -s -X POST localhost:8000/raw-samples -H 'Content-Type: application/json' \
  -d '{"name": "sample-B"}'
# {"batch_id":2,"kind":"raw","name":"sample-B"}

# 2. 创建混样：1 份批次 1 + 2 份批次 2
curl -s -X POST localhost:8000/mixes -H 'Content-Type: application/json' \
  -d '{"name": "mix-1", "recipe": [{"batch_id": 1, "portions": 1}, {"batch_id": 2, "portions": 2}]}'
# {"batch_id":3,"kind":"mix","name":"mix-1"}

# 3. 再混：5 份批次 3 + 3 份批次 1（批次 1 经两条路径进入，占比合并）
curl -s -X POST localhost:8000/mixes -H 'Content-Type: application/json' \
  -d '{"name": "mix-2", "recipe": [{"batch_id": 3, "portions": 5}, {"batch_id": 1, "portions": 3}]}'
# {"batch_id":4,"kind":"mix","name":"mix-2"}

# 4. 查询批次 4 的原始样本占比
curl -s localhost:8000/batches/4/composition
# {"batch_id":4,"kind":"mix","composition":[
#   {"raw_sample_id":1,"numerator":7,"denominator":12},
#   {"raw_sample_id":2,"numerator":5,"denominator":12}]}
# 即样本 A 占 7/12（5/8×1/3 + 3/8），样本 B 占 5/12（5/8×2/3）

# 5. 查询批次信息（含配方）
curl -s localhost:8000/batches/4
# {"batch_id":4,"kind":"mix","name":"mix-2","recipe":[{"batch_id":1,"portions":3},{"batch_id":3,"portions":5}]}
```

错误示例：

```bash
# 空配方 → 422
curl -s -X POST localhost:8000/mixes -H 'Content-Type: application/json' -d '{"recipe": []}'

# 非正份数 → 422
curl -s -X POST localhost:8000/mixes -H 'Content-Type: application/json' \
  -d '{"recipe": [{"batch_id": 1, "portions": 0}]}'

# 未知批次 → 400
curl -s -X POST localhost:8000/mixes -H 'Content-Type: application/json' \
  -d '{"recipe": [{"batch_id": 999, "portions": 1}]}'
# {"detail":"unknown batch id(s): [999]"}
```

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # 默认数据库文件为 ./data/lab.db
```
