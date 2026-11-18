# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`GET/POST /api/8`：可借目录演算预览，不落库。返回 report、digest、blocked。

`POST /api/8/publish`：{"text":"CSV内容"}。新批次生成新版本并原子切换为当前来源；同摘要批次复用旧版本；阻断批次409，空目录422，失败保留上一版。

`GET /api/8/catalog`：当前版本可借目录。`GET /api/8/versions`：版本历史与当前标记。

`POST /api/8/loans`：issn、year、issue、copy、partner。按当前版本出借并固定该版本；不可借或在借409。`GET /api/8/loans`：逐单核对当前目录。`POST /api/8/loans/{id}/return`：归还。

`GET /api/8/export`：发布证据CSV，含当前目录与旧单引用。`GET /api/8/sample`：基线与年度更新样例。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。

`GET /api/export/{id}`：唯一证据CSV。`GET /health`：存活检查。

错误：结构/数值422，版本冲突409，不存在404，文件过大413。逐行异常进入quarantine。
