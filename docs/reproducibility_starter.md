# Reproducibility proof: starter

- Command: `python -m yottaflex.generate --n-employees 500 --seed 20261022 --out <dir>`
- Seed 20261022, 500 employees, Python 3.10.11 on Windows-10-10.0.26200-SP0
- Files compared: 28 (CSV tables, ground truth, generation report, JSON and SQL exports)
- **Run A == Run B (row counts and SHA-256): True**
- Negative control (seed 20261023) differs: True

| file | rows | sha256 |
|---|---:|---|
| attrition_outcome.csv | 500 | `98183dad46abb0ca152d851734f6de881f8a8ff7fbd38aa0791ed8192674c5b7` |
| compensation_band.csv | 105 | `bab23a6c737a0e12014e14fc80a4ba7b3cf2697c1f0f2d57b14f6036534c05f1` |
| employee.csv | 500 | `5748cefc9d2089ea3b27ca4778d5cf16b01f14d83076f2472bd5db221a926cf9` |
| employee_team_assignment.csv | 536 | `df47da8044e23d05801d24db689451cf79823e5235169a6d09cd62b96b1b2e6c` |
| engagement_survey.csv | 3540 | `514ef7c9e5f52cfde33c8cc98dfe6ce3ebf4913bdf9fb9bc3a11a73caca1104d` |
| export/export_report.json |  | `c68084408f45697f7a2620a63bf9090659c930a627a5fa423ac1fa61455ab257` |
| export/json/attrition_outcome.json |  | `d718d84da6922be3100429618eed719f581bc7d69cb64fdd97ac9398fe9fb0a1` |
| export/json/compensation_band.json |  | `2744a9f5b3266033e5cb0e1292bd2b7ffbc86d8e72cc732a4bd7f5a6d27a42d2` |
| export/json/employee.json |  | `6afbf245e459684bf2a45da95cb3c0e65b5d5a933edbed51434f08721ae2f9cf` |
| export/json/employee_team_assignment.json |  | `f21b77b8d95b97a903b1e27c4a8fde030c4c8cd7b130f4eb1fcce8b62c277d6d` |
| export/json/engagement_survey.json |  | `5bed2aa4ec53df52d2a75ec7429fc7942a6047408015c3ae62610a1385a2c3cf` |
| export/json/intervention.json |  | `63cccfd2aa4fd5b7188d15f6c58f18d4c11f9db501baae6a5bb188bb409c1013` |
| export/json/promotion_history.json |  | `0be0af727cd7776cc0112ca240fe0308515ac6df4d98d68aaf8b605eba93eb9d` |
| export/json/role.json |  | `3b0e1c76f62563b5d3c81de306a55ab66e91860ad0b821875316880963dc1887` |
| export/json/team.json |  | `9753c94e0aa5b048ed1a47cb0aa4a89078826406b028d6108135d69185c785c5` |
| export/json/tenure_snapshot.json |  | `3268a5273cad99a117dc302f8166266aceb8ff03a6667ffb2828d264e2a3f888` |
| export/json/workload_snapshot.json |  | `1164865d3a2ec6e8e4718d14324c3fbdeffd3bc290facdcdedc91c2cc3045bf8` |
| export/schema.sql |  | `5c7a90dd24aaf019f5396946e30881f83b1514fa1afcedd39b7adc803021c6c9` |
| export/seed.sql |  | `9a78f21f9b954a20baae070bfbc545597360f4f65f53b215acdc2565dee17362` |
| generation_report.json |  | `b3727a2855bd30124a254e1922091be8934ff2bbbd5457d4386b0be9b06d0bea` |
| ground_truth.csv | 78 | `fa5642168cdd750ed4467e0440bbe834d6ecbcf6d6891b1fbcee1d69ef3b2341` |
| ground_truth.json |  | `08de9b829440441f2ce2713fcdd759e1e5b2588851f1ef469081a7ac22fd66cc` |
| intervention.csv | 39 | `7db0eb3a921e091ca94501c71a469ff1b567e7c0ae81a168a640eb6ec7a8ceec` |
| promotion_history.csv | 451 | `9eda9bfac1225cd2f55da6f0bcfc6905e00412aa8e22829ebc4eba001bc0c1cb` |
| role.csv | 35 | `61d01fac6550b0f1c404d9a1d2e4f10a666644d66ab92707be257e96b7e85831` |
| team.csv | 19 | `2573beb930cc38b8c3491b75105ba6d7bee14102d6f990cf79cb243851f6387c` |
| tenure_snapshot.csv | 3540 | `602819cb6d672afaaa1c77d480920c74473e1f87eff7ee247b9c38caceedf858` |
| workload_snapshot.csv | 3540 | `3839eb2644ba29c4c3bb22dc64c89e1a0693cfc53c0e5b0ed90ed609b51abfa9` |
