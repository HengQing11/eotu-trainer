# 地下蚁国修改器 (EotU Trainer)

《地下蚁国》(Empires of the Undergrowth, UE 4.27) 的游戏修改器，Python 编写。

## 功能

| 功能 | 生效层 | 说明 |
|---|---|---|
| 关卡内作弊开关 | 运行时（内存） | 打开官方调试位：无限资源 / 免费孵化 / 秒建 / 秒挖 |
| 蚁皇浆运行时补满 | 运行时（内存） | 游戏开着即时生效，锚点定位自动找玩家殖民地 |
| 蚁皇浆加点 | 存档（GVAS） | 需完全退出游戏，写入前自动备份 |
| 清除加点 | 存档（GVAS） | 一键清空全部加点（不退还蚁皇浆） |
| 蚁皇浆升级总表 | 数据表 | 从游戏数据生成的 HTML 总表 |

## 目录结构

```
├─ ui_new/app.py        # 正式版 GUI（PySide6 + QML，内嵌字符串）
├─ gui/                 # 旧版 GUI（customtkinter，保留可回退）+ 共用核心逻辑
│  ├─ core/             # 核心模块：内存读写 / 定位 / 存档 GVAS 解析 / 备份策略
│  └─ pages/            # 旧版页面
├─ scripts/             # 命令行工具与验证脚本（打包脚本也在这里）
├─ *.bat                # 双击入口（关卡作弊开关 / 蚁皇浆补满 / 更新表格等）
├─ *.csv                # 数值表（来自社区 mod pak 提取）
├─ 蚁皇浆升级总表.html  # 生成的升级总表
└─ PROJECT_HANDOFF.md   # 项目交接文档（技术栈/架构/体积分析，AI 可读）
```

## 技术栈

- Python 3.13.6
- PySide6 6.11.2 + QML（正式版 GUI）/ customtkinter（旧版）
- 打包：PyInstaller 6.22（onefile + windowed）

## 打包

```powershell
& <python路径> scripts/build_exe_qt.py
```

产物：`dist/蚁国修改器.exe`（约 157MB —— QML 引擎为固定成本，
体积分解与瘦身方案见 `PROJECT_HANDOFF.md` §6）。

## 运行时工作原理（简述）

- 通过 `ctypes` + toolhelp 快照定位 UE4 进程与模块基址
- 经 `GWorld → UWorld → ULevel → Actors` 遍历，用 vtable RVA 识别对象身份
- 作弊开关位于 `UGTileGrid +0x63A~0x63D`（官方调试 bool）；
  字段名与偏移来自 Dumper-7 生成的 SDK dump
- 对"游戏会周期性改回"的字段采用**持续按住（0.3s 重申）+ 每轮身份核对 + 期望状态表**策略

## 免责声明

仅供单机游戏学习与研究用途。请在离线/单机模式下使用，勿用于任何联机环境。
使用造成的存档问题请使用工具自带的自动备份回退。
