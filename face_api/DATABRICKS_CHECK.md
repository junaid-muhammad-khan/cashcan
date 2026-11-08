# Databricks database check (100 photos of 100 different people)

Pipeline: real face model -> quality gates -> match with threshold 0.45, margin 0.05. 30 people (90 templates) enrolled in `workspace.cashcan_faces`; 100 probe photos (30 are a different photo of an enrolled person, 70 are people who are not enrolled). 5 candidate people were skipped because their photos failed the quality gates.

| Check | Local matching (templates pulled from Databricks) | Databricks Vector Search |
|---|---|---|
| Enrolled person recognised | 29/30 | 29/30 |
| Enrolled person given the wrong name | 0/30 | 0/30 |
| Stranger accepted | 0/70 | 0/70 |

**The two lookups agree on 100/100 photos.**

Photos that were not handled perfectly:

- Paula_Radcliffe (enrolled): local -> None (below_threshold, 0.37); Vector Search -> None (below_threshold, cosine 0.37)

| Timing | Value |
|---|---|
| Push 30 people / 90 templates (bulk) | 23s |
| Vector Search caught up after the push | 123s |
| Pull all templates from Delta | 2.8s |
| Vector Search query, mean / 95th percentile | 246 ms / 307 ms |

(Public-benchmark photos of real people; test rows were deleted afterwards. LFW is easier than a bin webcam.)

Cleanup: 30 test people deleted; remaining test rows in the database: users=0, templates=0.
