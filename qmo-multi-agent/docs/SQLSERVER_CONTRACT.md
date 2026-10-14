# SQL Server view contract

Create a read-only dbo.qmo_agent_metrics_vw in your QMO database. Physical columns
must be confirmed and mapped from your approved existing sources.

| Column | Meaning |
|---|---|
| portfolio | Authorized portfolio name |
| application | Name/ID consistent with API scope |
| period | Reporting month YYYY-MM |
| scorecard | maturity or product_quality |
| metric | Governed KPI name |
| value | Nullable numeric value |
| unit | percent, count, score, etc. |
| status | Governed Green/Amber/Red/No Data |
| refreshed_at | Actual source refresh timestamp |

Require one record per application/period/scorecard/metric and historical snapshots.
Potential sources, after schema verification: Digital_QMO_KPI_Metrics,
digital_dev_artifacts_maturity_scorecard, Digital_Dev_Artifacts_Quality_ScoreCard,
digital_qmo_maturity_summary_view, product_quality_summary_vw_v3 and
 dbo_dev.digital_color_threshold. Join Product_Team_Artifacts for dev leader only
after checking join cardinality. Use approved normalization rules, preserving raw
missing values. Restrict database credentials to authorized read access. Model
queries cannot select arbitrary SQL or override server scope.
