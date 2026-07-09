// ================ 新闻报道 导入脚本 ================

// 导入节点
:auto USING PERIODIC COMMIT 100
LOAD CSV WITH HEADERS FROM 'file:///新闻报道/case_id.csv' AS row
MERGE (w:WorkOrder {id: row.case_id});

:auto USING PERIODIC COMMIT 100
LOAD CSV WITH HEADERS FROM 'file:///新闻报道/city.csv' AS row
MERGE (c:City {name: row.city});

:auto USING PERIODIC COMMIT 100
LOAD CSV WITH HEADERS FROM 'file:///新闻报道/department.csv' AS row
MERGE (d:Department {name: row.department});

// 导入关系
:auto USING PERIODIC COMMIT 100
LOAD CSV WITH HEADERS FROM 'file:///新闻报道/workorder_city.csv' AS row
MATCH (w:WorkOrder {id: row.workorder_id}), (c:City {name: row.city_name})
MERGE (w)-[:LOCATED_IN]->(c);

:auto USING PERIODIC COMMIT 100
LOAD CSV WITH HEADERS FROM 'file:///新闻报道/workorder_department.csv' AS row
MATCH (w:WorkOrder {id: row.workorder_id}), (d:Department {name: row.department_name})
MERGE (w)-[:HANDLED_BY]->(d);