# PROJECT_HANDOFF.md — 地下蚁国修改器 交接报告

> 生成于 2026-09-17 10:10，基于对实际代码与 dist 产物的逐文件扫描。
> 接手前请先读完「⚠️ 安全铁律」与「已知坑」，那里全是踩过的雷。

---

## 0. 项目是什么

《地下蚁国》(Empires of the Undergrowth, UE 4.27.2) 的单机修改器，功能：

| 功能 | 层 | 状态 |
|---|---|---|
| 官方调试开关（无限资源/免费孵化/秒建/秒挖） | 内存写 UGTileGrid+0x63A~0x63D | ✅ 正式版 |
| 蚁皇浆运行时补满（20 亿） | 内存写 colony+0x89C | ✅ 正式版 |
| 清除加点（一键清零存档加点） | 存档 GVAS 编辑 | ✅ 正式版 |
| 蚁皇浆加点/加点详情（存档表格编辑） | 存档 GVAS 编辑 | ⏸ 旧版页面，代码在 gui/pages/adaptations.py |
| 更新表格链（从 mod pak 提数值生成总表） | 离线工具链 | ✅ 独立 bat |

**当前唯一正式入口/交付物：`dist/蚁国修改器.exe`（156.8MB，QML v3.0.0）**

---

## 1. 技术栈

| 项 | 值 | 依据 |
|---|---|---|
| Python | **3.13.6**（系统版 `C:\Users\beimo\AppData\Local\Programs\Python\Python313\python.exe`） | build 脚本与打包日志均用此解释器；托管版 3.13.12 不用于本项目 |
| GUI（正式版） | **PySide6 6.11.2 + QML**（QtQuick/QuickControls2/Basic style） | `ui_new/app.py`（QML 以 Python 字符串内嵌） |
| GUI（旧版，保留回退） | customtkinter（浅色→已改黑）+ tkinter ttk | `gui/main.py`、`gui/theme.py` |
| 图形引擎 | Qt6（QtQuick 渲染） | exe 内归档证实 |
| 打包 | **PyInstaller 6.22.3**（contrib hooks 2026.7），**onefile + windowed** | `build_pyi_qt/20260917_081352/蚁国修改器.spec` |
| 其它三方 | 无（无 requirements.txt；除 PySide6/customtkinter 外全部为标准库） | 全项目 import 扫描 |

注意：`mod/.pylibs/` 里有一份 pywebview/eel 残留（已终止的瘦身实验），与正式版无关。

---

## 2. 目录结构

```
mod/
├─ ui_new/                    ★ 当前正式版源码（QML v3）
│  ├─ app.py                  唯一入口：QML 字符串 + Backend(QObject) + 主函数
│  └─ mockup.py               早期效果图草稿（可删）
├─ gui/                       旧 CTk 版完整源码（可回退，勿删）
│  ├─ main.py                 旧入口（PAGES 注册制 + 左导航）
│  ├─ theme.py / widgets.py   主题色表与控件库
│  ├─ pages/                  adaptations(加点详情) / cheats(作弊) / creature_stats
│  └─ core/                   ★★ 全部核心逻辑（新旧两版共用）
│     ├─ memscan.py           ctypes 内存读写/进程扫描引擎
│     ├─ cheats.py            官方开关定位+读写+蚁皇浆锚点定位/补满（vtable RVA）
│     ├─ gvas.py              存档 GVAS 解析/写（set_bool/set_int/get_int）
│     ├─ jelly.py             加点字段映射、浆槽位、费用计算
│     ├─ fieldlib.py          升级项字段库（读 升级项字段库.csv）
│     ├─ actions.py           存档写入总闸：游戏运行拒写→备份→写→回读校验
│     ├─ backup.py            自动备份（每文件保留 max_backups=5 份）
│     ├─ saves.py / paths.py  存档枚举/显示名、路径与配置（config.json）
│     ├─ gameproc.py          游戏进程状态检测
│     └─ live.py / winproc.py 旧版运行时辅助（bat 用）
├─ scripts/                   31 个工具脚本（详见 §6）
│  ├─ build_exe_qt.py         ★ 打包 QML 版（当前正式打包脚本）
│  ├─ build_exe.py            旧 CTk 版打包脚本
│  ├─ cheat_flags.py          bat 版开关保活（food_chamber 依赖）
│  ├─ jelly_live.py           bat 版浆锚点定位（与 gui/core/cheats.py 同源）
│  ├─ shot_win.py / shot_printwindow.py  窗口截图（后者支持 frameless）
│  └─ update_all.py 等        表格链
├─ tools/dumper7/             Dumper-7.dll + inject.py（SDK 生成器，重生成 C:\Dumper-7）
├─ dist/                      ★ 交付物
│  ├─ 蚁国修改器.exe          156.8MB（onefile）
│  ├─ config.json             运行配置（game_dir/save_file/max_backups=5/jelly_cap）
│  ├─ data/                   打包时内嵌释放的 升级项字段库.csv 等
│  └─ selftest.txt            --selftest 输出
├─ origin/ sources/           官方 pak 副本与社区 mod 提取源（表格链输入）
├─ 升级项字段库.csv            加点字段唯一权威源（136 项）
├─ 蚁皇浆升级总表.html         生成的总表（用户明确要求保留）
├─ 待整合模块.md              模块状态 + 🔒22 项禁删清单
├─ 关卡作弊开关.bat / 关卡作弊-关闭.bat / 运行时补满蚁皇浆.bat   轻量入口
├─ .pylibs/                   ⚠️ 瘦身实验残留（6 个删不掉的 dll/pyd，~1.5MB，待手删）
├─ build_pyi_qt/              ⚠️ PyInstaller 工作目录（~1.4GB，含历次构建，可整删）
├─ build_pyi/                 旧 CTk 打包工作目录（22.8MB，可删）
└─ backup/                    ~970MB 历史备份（含全部旧版 exe，谨慎瘦身）
```

---

## 3. 程序入口与架构

**正式入口：`ui_new/app.py`**（打包入口同一文件）
- `main()`：创建 QML 窗口（frameless, 1160×720）→ `Backend` 注入 QML 上下文 → `app.exec()`
- `selftest()`：`--selftest` 不开界面自检（版本/存档/游戏状态/备份上限/加点清单），写 exe 同级 selftest.txt

**三层结构（逻辑与界面完全分离）**：

```
ui_new/app.py  ──QML(内嵌字符串)──  页面卡片/开关/下拉（纯展示）
     │ ↑↓ 调用
     │  Backend(QObject)：后台线程 0.3s 轮询
     ▼
gui/core/*  ── 核心逻辑（QML 版与 CTk 旧版共用同一份）
     │  cheats.py     定位(网格/殖民地锚点) + 开关读写 + 浆补满
     │  actions.py    存档写入总闸（备份/校验/拒绝游戏运行时写）
     │  memscan.py    进程句柄、ReadProcessMemory/WriteProcessMemory
     ▼
游戏进程(EotU-Win64-Shipping.exe) / 存档文件(%LOCALAPPDATA%\EotU\Saved\SaveGames)
```

**线程/异步模型**（ui_new/app.py Backend）：
- 后台守护线程 0.3s 一轮：①按 `wants` 期望表重申 4 个开关（对峙：游戏会周期改回）
  ②每 4 轮做重读取（资源/浆/殖民地重锚定）③每轮 `_grid_ok()` 身份核对（vtable RVA），
  失效立即重新定位
- 退出时 `cleanup()`：把 4 个开关清零（关工具=自动关作弊），然后关句柄
- 关键防线：写入前必须核对对象身份（**vtable 指针必须读满 8 字节**）；
 殖民地/网格定位 = 同 vtable 候选中取**容量最小**者；浆用打分锚点（与浆值无关）

**存档操作链**（清除加点）：
`game_running() 拒写 → gvas.SaveFile → jelly.addons() 找全部已加点项 → 全部置 0 →
backup_file（保留5份）→ 写盘（长度必须不变）→ 重新加载回读校验`

---

## 4. 依赖与打包

### 实际三方依赖
- 正式版运行：**仅 PySide6**
- 旧 CTk 版：customtkinter（+tkinter）
- 打包：pyinstaller
- 其余 imports 全部是本地模块或标准库（已逐文件扫描确认）

### 打包方式（scripts/build_exe_qt.py）
```
pyinstaller --noconfirm --onefile --windowed --name 蚁国修改器
  --hidden-import PySide6.QtQuick --hidden-import PySide6.QtQuickControls2
  --hidden-import PySide6.QtNetwork
  --exclude numpy/matplotlib/QtWebEngineCore/QtWebEngineWidgets/QtWebChannel/Qt3D/tests
  ui_new/app.py
```
- ⚠️ QML 内嵌在 Python 字符串里，静态分析看不到 → QtQuick 等**必须 hidden-import**
- ⚠️ 不要 `--clean`（沙箱拦批量删除）；工作目录带时间戳；打包前先把 dist 旧 exe 移走
- ⚠️ `PySide6.QtQmlModels` 在 6.11 不存在，hidden-import 会报错
- spec 实际内容：onefile、windowed、upx=True（未装 UPX 故未生效）、console=False

---

## 5. 150MB 体积分析（解析 exe 内 CArchive 归档得出，精确数字）

exe 156.8MB = 2843 个条目压缩后；条目**未压缩合计 394.2MB**。

| 成分 | 未压缩体积 | 说明 |
|---|---|---|
| **WebEngine 系列 23 个文件** | **195.1MB** | Qt6WebEngineCore.dll 单文件 79.4MB —— 内置浏览器内核，**完全未使用**（`--exclude-module` 只挡 import，挡不住二进制被钩子连带打包）|
| opengl32sw.dll ×1 | 19.7MB | 软件渲染后备，可去（牺牲无 GPU 时的兜底）|
| Quick3D 563 个文件 | 13.5MB | 未使用 |
| Qt6Pdf ×2 | 5.0MB | 随 WebEngine 连带 |
| Qt 必需件（Core/Gui/Quick/Qml/Network/ShaderTools/Controls…） | ~110MB | 真正需要的 |
| python313.dll + 标准库 PYZ | ~4.4MB | |
| 项目代码 | <0.5MB | |

### 瘦身结论（已量化，未实施）
- 在 spec 里**过滤 binaries/data**（而非 exclude-module）：剔除 `*WebEngine*`、`*Quick3D*`、
  `Qt6Pdf*`、`opengl32sw*` 共 **233.2MB（未压缩口径）**
- 预估瘦身后 **exe ≈ 59~64MB**；QML 动效/功能零损失
- 方法：`build_exe_qt.py` 改为直接操作 spec，在 `EXE(...)` 前对 `a.binaries`、`a.datas`
  做 TOC 过滤（PyInstaller 标准做法）

---

## 6. scripts/ 一览（31 个，按用途）

- **打包**：build_exe_qt.py（正式）、build_exe.py（旧 CTk）
- **开关/运行时（bat 后端）**：cheat_flags.py、jelly_live.py、food_chamber.py（旧定位）、
  ue_walk.py、try_food.py（基础连接/格式化）
- **表格链**（更新表格.bat → update_all.py）：build_field_lib.py、gen_jelly_table.py、
  gen_ngp_report.py、merge_html.py、field_lib.py、build_official_overrides.py、official_overrides.py
- **分析/一次性**：shot_win.py、shot_printwindow.py、field_hunt.py、dt_parse.py、ue4dt.py、
  refill_jelly.py、patch_sav.py、sav_props.py、jelly_calc.py、gen_ngp_report.py 等
- ⚠️ `update_all.py` 用 subprocess 串脚本 —— AST 扫 import 会误判孤儿

---

## 7. ⚠️ 安全铁律与已知坑（接手必读）

1. **不对游戏用调试器**（DebugActiveProcess/硬件断点两次把游戏搞崩，0x80000004）
2. **读指针必须读满 8 字节**（读 4 字节 = 指针低半部，地址校验永远失败）
3. **写内存前必须核对对象身份**（vtable RVA），且网格/殖民地会随换关重建
4. 游戏会**周期性改回** InfinateResources（~0.4s）→ 开关必须持续按住（0.3s 轮），
   单次写入对"会自己改值的字段"一律无效（食物账本同理）
5. 存档操作：游戏运行时**拒绝写入**；写入前自动备份；写后回读校验
6. 本环境 safe-delete 层：拦截一切删除（fail-closed），**对 .dll/.pyd 必拦**；
   其 FAILED 报告不可信，删后必须 Test-Path 复验；打包前先 mv 走 dist 旧 exe
7. pywebview 事件处理器存弱引用（lambda 会被 GC）；WebView2 画面 BitBlt/PrintWindow
   抓不到（DirectComposition）—— C 方案（WebView 瘦身壳）因此终止，代码在 backup/2026-09-17/
8. exe 是 onefile，双击后 ~20-30s 解压才出窗口，不是卡死
9. Git Bash 里不能调 cmd.exe；`timeout` 会解析到 Windows 的 timeout.exe
10. `dist/config.json` 是打包态配置（max_backups 等），exe 读它，别用源码目录的顶替

---

## 8. 眼下的待办/残留

- [ ] `.pylibs/`（1.5MB）剩 6 个删不掉的 dll/pyd —— 用户手动 `rd /s /q` 即可
- [ ] `build_pyi_qt/` ~1.4GB PyInstaller 中间产物 —— 可整目录删
- [ ] `backup/` ~970MB —— 历史版本，瘦身前先确认不需要回退
- [ ] 瘦身打包（§5 方法，预估 59~64MB）—— 已量化未实施
- [ ] `ui_new/mockup.py` 可删
