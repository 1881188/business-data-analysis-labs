# 工作表迁移对照

原工作簿只读；缓存是教材保存的快照，不等于本次重算。

| 来源键 | 工作表 | 教学内容与Python去向 |
|---|---|---|
| etl_append_different | 第一季度 | concat显式对齐字段；金额仅在此受控示例映射为销售额，不猜测门店A/A1对应 |
| etl_append_different | 第二季度 | concat显式对齐字段；金额仅在此受控示例映射为销售额，不猜测门店A/A1对应 |
| etl_append_same | 第一季度 | concat显式对齐字段；金额仅在此受控示例映射为销售额，不猜测门店A/A1对应 |
| etl_append_same | 第二季度 | concat显式对齐字段；金额仅在此受控示例映射为销售额，不猜测门店A/A1对应 |
| etl_course_join | 学生表 | 学生和课程维度键唯一，选课记录作事实，关联后行数守恒；不把选课行数当去重人数 |
| etl_course_join | 课程表 | 学生和课程维度键唯一，选课记录作事实，关联后行数守恒；不把选课行数当去重人数 |
| etl_course_join | 选课表 | 学生和课程维度键唯一，选课记录作事实，关联后行数守恒；不把选课行数当去重人数 |
| etl_dirty_orders | Sheet2 | 空白工作表，不生成伪造记录 |
| etl_dirty_orders | Sheet3 | 空白工作表，不生成伪造记录 |
| etl_dirty_orders | sheet1 | 去标题行、保留源行号，空白/错误/真实零分开；源ip地址字段不强行解释为IP |
| etl_split_orders | Sheet2 | 订单号横向拆列、地址和数量拆分；另建不带数量的订单桥，保持原行粒度 |
