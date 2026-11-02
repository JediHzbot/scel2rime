# Agent 调用与验收

这些接口供本地 agent 串联使用，不向 DSH 或其他服务发送词库。当前尚未提供自动推断所有搜狗安装位置的一键 `migrate.ps1`；调用者必须检查扫描覆盖与格式报告。

## 建议流程

1. `scel2rime scan --include D:\词库 --json`，检查 `roots`、`searched_roots`、`errors` 和 `files`。扫描发现文件不等于格式验证。
2. 对确认的输入执行 `scel2rime convert ... -o 本次新建输出目录 --dry-run --json`。检查每个 `results`；失败或部分恢复时停止自动安装。
3. 正式转换到本次独立目录，要求退出码 0，并逐项检查 `complete=true`、`status=converted`、`written=true`。不要复用含历史残留词典的输出目录。
4. `install.ps1 -From 本次输出目录 -DryRun -Json`，审阅目标目录和待覆盖清单。
5. `install.ps1 -From 本次输出目录 -Deploy -Json`。要求 `exit_code=0`、`status=compiled`，保留 `backup_dir`。`installed` 仅代表文件已安装。
6. 选择若干有区分度的原词条，验证全拼候选、多音字、简繁切换；按实际需求验证缩写、联想和词频排序。编译通过不替代这一步。

## Python CLI 退出码

| 码 | 含义 | 自动流程动作 |
|---|---|---|
| 0 | 完整成功，或预演通过 | 仍检查 operation 和 dry_run，避免把预演当执行 |
| 1 | 有失败、冲突、缺失输入或无可处理文件 | 停止安装，检查逐文件原因 |
| 2 | 参数错误 | 修正调用 |
| 3 | 有部分恢复 | 等待人工检查，不自动部署残缺词库 |

JSON `schema_version=1`；`results` 包含来源、目标、状态、实际是否写入、解析条数、去重后条数、完整性和警告。未解析成功的记录不具有完整词典字段，调用者不能假定每条记录都有 `entries` 或 `destination`。

`--force` 仅允许替换上次输出，不允许同一批次互相覆盖。`--allow-partial` 只用于明确的数据恢复，不会把退出码变为 0。

## 恢复

安装或部署失败后，检查 `status` 是否为 `rolled_back`。如果是 `rollback_failed`，保留现场和备份，检查 `error`、`rollback_error`，不要无限重试。手动恢复使用 `rollback.ps1 -BackupDir 单次快照完整路径 -Json`。
