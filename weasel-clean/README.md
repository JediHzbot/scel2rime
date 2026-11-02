# weasel-clean

给已安装的 Weasel（小狼毫）应用本地配置与迁移词库。脚本不下载安装程序，不注册输入法，也不修改搜狗文件。

## 前提与边界

- Windows，Python 转换器需要 Python 3.10+；安装脚本需要 Windows PowerShell 5.1 或 PowerShell 7。
- 先安装并启动一次 [Weasel](https://github.com/rime/weasel/releases)，建立 Rime 用户目录。
- 配置会替换三份 `.custom.yaml`，不是与现有键位、皮肤、方案逐项合并。所有被替换文件都进入本次备份。
- 对自定义位置显式传入 `-RimeUserDir` 和 `-WeaselRoot`。自动寻找只覆盖 Program Files 下的 Rime 安装目录。
- 若输入法正在占用编译文件，部署可能失败并恢复。应先关闭占用，再重试；脚本不会强行结束输入法服务。

## 安装与预演

```powershell
.\install.ps1 -From ..\rime-dicts -DryRun -Json
.\install.ps1 -From ..\rime-dicts -Deploy -Json

# 自定义位置；同一个目录会传给部署器
.\install.ps1 -RimeUserDir D:\Rime -WeaselRoot D:\Apps\Weasel -From ..\rime-dicts -Deploy -Json

# 只安装默认配置和基础聚合词典，不进行编译
.\install.ps1
```

`-DryRun` 完成输入与命名检查，不创建备份、锁文件或任何配置。`-From` 不存在或为空、文件名与头部 name 不一致、含保留词典名时，预检失败，不改配置。保留名包括 `scel_merged` 和基础词典名。

安装器会：

1. 读取并检查所有输入；准备配置、词典和聚合词典。
2. 锁定本目录，备份所有将被覆盖的文件，记录哪些目标原本不存在。
3. 校验备份 SHA-256，保存唯一的 `backup-scel2rime-时间-随机值/manifest.json`。
4. 应用配置；可选编译。任何已捕获的写入或编译错误都会触发自动恢复。

突发断电或安装进程被外部强杀，无法保证自动恢复完成；保留的清单支持下次手动恢复。

## 部署与成功判定

```powershell
.\deploy.ps1 -UserDir D:\Rime -WeaselRoot D:\Apps\Weasel -TimeoutSeconds 120 -Json
```

部署器会备份 `build`、`installation.yaml`、`user.yaml`，从空的 build 开始全量编译。`-FullCheck` 保留为兼容参数；现在每次都是全量编译，不以旧缓存作为成功证据。

调用 `rime.dll` 的代码位于独立的 `deploy-worker.ps1` 进程。部署器等待进程退出、限制最长运行时间，检查本次原生日志是否有 ERROR/FATAL，再验证以下新产物非空：

- `scel_merged.table.bin`
- `luna_pinyin_simp.prism.bin`
- `luna_pinyin_simp.schema.yaml`，且引用 `scel_merged`

日志保存在本次部署备份目录。失败或超时恢复旧编译目录及上述元数据；由安装器调用时，还会恢复安装前的配置和词典。诊断日志和备份保留，不进行自动清理。脚本不备份或迁移个人学习数据库，不提供对任意第三方插件副作用的事务保证。

JSON 状态：`planned` 预演通过；`installed` 文件已安装但未编译；`compiled` 新编译产物检查通过；`rolled_back` 失败且已恢复；`rollback_failed` 恢复未完成，需要按备份检查。退出码 0 表示该操作通过，1 表示失败。**`compiled` 不等于已验收实际候选、词频或简繁切换。**

## 精确回滚

只使用本次 JSON 返回的 `backup_dir`，不要把多个时间点的备份混在一起：

```powershell
.\rollback.ps1 -BackupDir 'D:\Rime\backup-scel2rime-实际时间-实际编号' -DryRun -Json
.\rollback.ps1 -BackupDir 'D:\Rime\backup-scel2rime-实际时间-实际编号' -Json
```

回滚先校验整份备份，再恢复原文件并删除该次操作新增的受管文件。包含 build 的快照也恢复旧 build；只安装未编译的快照不涉及 build。回滚会覆盖该次操作之后对这些受管文件的编辑，请先保存需要保留的修改。恢复的是磁盘状态；正在运行的输入法可能需要重新加载。

## 配置内容

候选数 9、横排、纯色配色、Shift 提交当前编码后切换英文、开启本地用户词库、使用 `luna_pinyin_simp`。迁移词典通过 `scel_merged` 聚合。此配置包不是独立输入法。

## 验证范围

参见 [验证记录](../docs/validation.md)。现有真实引擎验证基于 Weasel 0.17.4 / librime 1.13.1；不能据此推断其他版本全部兼容。Windows 10、其他架构、真实大词库仍需要单独验收。
