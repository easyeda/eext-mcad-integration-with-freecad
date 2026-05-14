[简体中文](#)

# FreeCAD 机电协同 —— 嘉立创 EDA 专业版扩展

通过 WebSocket 实现 PCB 3D 模型在嘉立创 EDA 与 FreeCAD 之间的实时协同。支持模型导出、双向位置同步、交叉定位、删除同步。

## 功能特性

| 功能      | 说明                                 |
| ------- | ---------------------------------- |
| 3D 模型导出 | 将 PCB 的 STEP 模型分片传输到 FreeCAD，支持大文件 |
| 下载脚本文件  | 一键保存 FreeCAD 宏脚本到本地，免去手动复制          |
| 双向位置同步  | EDA 拖动元件 → FreeCAD 跟着动，反之亦然        |
| 交叉定位    | 点击一边的元件，另一边自动聚焦                    |
| 删除同步    | EDA 删除元件，FreeCAD 同步移除              |
| 位号重命名   | 改名后映射自动更新                          |
| 导入心跳保活  | 大文件导入期间持续发送进度，防止超时断连               |

***

## 环境要求

| 项目          | 要求              |
| ----------- | --------------- |
| 嘉立创 EDA 专业版 | ≥ 3.0           |
| FreeCAD     | ≥ 1.0           |
| 网络          | 本机可用（localhost） |

***

## 安装步骤

### 第一步：安装 FreeCAD 宏脚本

1. 打开 **FreeCAD**
2. 顶部菜单栏点击 **宏** → **宏编辑器**（或按 `Alt+F8`）
   ![FreeCAD 打开宏编辑器的菜单位置](images/1.jpg)
3. 在宏编辑器中点击 **新建**（或 `Ctrl+N`）创建新宏
4. 打开本项目 [script/Interactive-with-easyeda.py](https://github.com/easyeda/eext-mcad-integration-with-freecad/blob/main/script/Interactive-with-easyeda.py) 文件，将全部内容复制粘贴到宏编辑器中（脚本文件也可以通过菜单 **FreeCAD机电协同** → **下载脚本文件**，一键保存到本地）

![](images/12.jpg)

5. 点击 **保存**（`Ctrl+S`），将宏命名，保存到默认宏目录
6. 点击 **执行或双击执行**（绿色三角形按钮，或 `Ctrl+F5`）运行脚本
   ![操作流程](images/2.jpg)
7. **验证启动成功**：点击 **视图** → **面板** → 勾选 **报告视图**，在底部报告视图中应看到：

```
检查websockets库...
websockets库已安装
初始化WebSocket服务器 0.0.0.0:8766
WebSocket服务器启动成功!
地址: ws://localhost:8766
FreeCAD环境已检测，服务器已启动
已注册主线程定时器（100ms轮询消息队列）
已注册位置监听定时器（500ms轮询位置+选中+删除）
等待客户端连接...
```

> **提示：** 脚本会自动检测并安装 `websockets` Python 库。首次运行可能需要几秒钟安装依赖。如果自动安装失败，见下方常见问题。

### 第二步：安装 EDA 扩展

1. 打开 **嘉立创 EDA 专业版**
2. 安装完成后，在扩展列表中找到 **FreeCAD机电协同**，确认已启用
 **开启外部交互权限**：点击 **扩展** → **扩展设置** → 开启 **外部交互** 权限（WebSocket 通信需要）
![](images/4.jpg)

## 使用教程

### 一、导出 3D 模型到 FreeCAD

确保 FreeCAD 宏脚本已运行，然后在 EDA 中：

1. 打开一个 PCB 设计文件，进入 **PCB 编辑器**
2. 顶部菜单点击 **FreeCAD机电协同** → **导出3D到FreeCAD**

![菜单点击位置](images/3.jpg)

1首次使用会自动连接 FreeCAD 服务器，看到提示「正在连接到FreeCAD服务器...」

![连接提示](images/5.jpg)

2 连接成功后自动获取 STEP 文件并分片上传，看到提示「PCB STEP文件获取成功」

3 上传完成后 FreeCAD 开始导入，EDA 显示「正在导入STEP文件到FreeCAD...」

![进行中](images/11.jpg)

4 导入完成，EDA 显示「PCB导入完成」，FreeCAD 中显示 3D 模型

![FreeCAD 中导入成功的 3D 模型](images/6.jpg)

> **注意：** 大文件（元件多、3D 模型复杂）导入可能需要数分钟。导入期间 FreeCAD 界面会无响应，这是正常现象。后台心跳会持续保活连接，不会断开。

### 二、启用双向交互

导出模型后，可以启用双向交互实现实时同步：

1 点击菜单 **FreeCAD机电协同** → **启用双向交互**

![菜单点击位置](images/3.jpg)

2 EDA 会自动将元件位号与 FreeCAD 3D 对象建立映射（三轮匹配：精确匹配 → 正则匹配 → 位置匹配）
3 映射成功后看到提示「双向交互已启动
![双向交互已启动](images/7.jpg)
    此时可以：
   - **在 EDA 中拖动元件** → FreeCAD 中的 3D 模型实时跟随移动
   - **在 FreeCAD 中拖动对象** → EDA 中的元件同步移动
   - **在 EDA 中点击元件** → FreeCAD 自动选中并聚焦
   - **在 FreeCAD 中点击对象** → EDA 自动定位到对应元件

![双向同步效果](images/9.jpg)

### 三、停止双向交互

1. 点击菜单 **FreeCAD机电协同** → **停止双向交互**
![双向交互已停止](images/10.jpg)
2. 所有映射关系和监听会被清除

### 四、连接管理

| 菜单选项         | 功能                   |
| ------------ | -------------------- |
| 导出3D到FreeCAD | 自动连接 + 分片上传 + 导入     |
| 启用双向交互       | 开启实时双向同步             |
| 停止双向交互       | 关闭同步并清理映射            |
| 连接FreeCAD    | 手动建立 WebSocket 连接    |
| 断开FreeCAD    | 断开连接（菜单由 EDA 扩展框架提供） |
| 检查FreeCAD连接  | 查看当前连接状态             |

***

## 技术说明

| 项目   | 说明                                         |
| ---- | ------------------------------------------ |
| 通信协议 | WebSocket（JSON），地址 `ws://localhost:8766`   |
| 文件格式 | STEP (.step)                               |
| 文件传输 | 512KB 分片 Base64 编码，支持大文件                   |
| 线程模型 | FreeCAD 主线程（QTimer）+ WebSocket 异步线程 + 消息队列 |
| 导入保活 | 后台心跳线程每 2 秒发送进度，防止大文件导入超时                  |

***

## 常见问题

### 连接 FreeCAD 失败

请按顺序检查：

1. **FreeCAD 是否已启动**，且宏脚本已运行
2. **端口 8766 是否被占用** — 如果上次 FreeCAD 非正常关闭，端口可能残留。关闭所有 FreeCAD 进程后重试
3. **外部交互权限** — EDA 扩展设置中是否已开启外部交互权限
4. **防火墙** — 检查 Windows 防火墙是否拦截了 8766 端口

### websockets 库自动安装失败

手动安装：

```shell
执行命令示例
"<FreeCAD安装目录>/bin/python.exe" -m pip install websockets==13.1 -i https://pypi.tuna.tsinghua.edu.cn/simple

Windows 示例
"C:\Program Files\FreeCAD 1.1.1\bin\python.exe" -m pip install websockets==13.1 -i https://pypi.tuna.tsinghua.edu.cn/simple

macOS 示例
"/Applications/FreeCAD.app/Contents/Resources/bin/python3" -m pip install websockets==13.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 导入大文件时 FreeCAD 卡住

这是正常现象。FreeCAD 的 STEP 解析使用 OpenCASCADE 内核，是单线程的。80 个对象的 PCB 通常需要数分钟。导入期间：

- FreeCAD 界面会无响应
- EDA 端会收到 `import_progress` 心跳消息（控制台可见）
- 导入完成后 FreeCAD 自动恢复响应

**加速建议：** CPU 单核性能越高越快；内存充足避免磁盘交换。

### 导入后 FreeCAD 报告视图有错误

点击 **视图** → **面板** → **报告视图** 打开日志面板，查看详细错误信息。常见问题：

- STEP 文件不完整 → 重新导出
- FreeCAD 版本过低 → 升级到 1.0 以上

### 双向交互位置不同步

1. 确认已经 **先导出模型**，再启用双向交互
2. 检查 FreeCAD 报告视图中映射日志，确认元件匹配数量
3. 如果匹配数为 0，可能是位号格式不标准，尝试在 FreeCAD 中检查对象的 Label

***

## 项目结构

```
pcb-export-to-freeCad/
├── src/
│   └── index.ts                         # EDA 扩展主逻辑（TypeScript）
├── script/
│   ├── Interactive-with-easyeda.py      # FreeCAD WebSocket 服务器（Python 宏）
│   ├── eda_api_reference.md             # EDA 扩展 API 参考手册
│   └── PCB-FreeCAD双向协同实践.md         # 技术博客文章
├── config/
│   ├── esbuild.common.ts                # 构建配置
│   └── esbuild.prod.ts
├── build/
│   ├── packaged.ts                      # 打包脚本
│   └── dist/
│       └── mcad-integration-with-freecad_v1.0.0.eext  # 发布包
├── locales/
│   ├── zh-Hans.json                     # 中文翻译
│   └── en.json                          # 英文翻译
├── images/
│   └── logo.png                         # 扩展图标
├── extension.json                       # 扩展配置清单
├── package.json
└── tsconfig.json
```
