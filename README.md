[简体中文](#) | [English](./README.en.md)

# 导出至FreeCAD

通过 WebSocket 将 PCB 3D 模型（STEP 格式）发送到 FreeCAD 进行查看和编辑。

## 功能特性

- 通过 WebSocket 将 PCB 3D 模型导出到 FreeCAD
- 支持 STEP 格式导出
- 自动安装 Python 依赖
- 进度条展示
- 简单易用的菜单操作

## 快速开始

### 1. 安装 FreeCAD WebSocket 服务器脚本

#### 使用宏运行脚本

1. **打开 FreeCAD**
2. 在顶部菜单栏点击 **宏** → **宏编辑器**
3. 在宏编辑器中：
   - 点击 **新建** 创建新宏
   - 将 `script/pcb_importer_freecad.py` 的内容粘贴进去
   - 点击 **保存**，命名为 `pcb_importer`
   - 点击 **执行** 运行脚本

脚本会自动检测并安装 `websockets` 依赖，无需手动操作。

运行成功后会看到类似如下输出：

```
检查websockets库...
websockets库已安装
初始化WebSocket服务器 0.0.0.0:8766
WebSocket服务器启动成功!
地址: ws://localhost:8766
FreeCAD环境已检测，服务器已启动
已注册主线程定时器（100ms轮询）
等待客户端连接...
```

### 2. 安装扩展

1. **在嘉立创EDA专业版中安装**：
   - 打开嘉立创EDA专业版
   - 点击 **扩展** → **扩展管理**
   - 点击 **安装扩展** → **从本地文件安装**
   - 选择 `build/dist/pcb-export-to-freecad_v1.0.0.eext`
   - 启用扩展并开启外部交互权限

### 3. 使用扩展

1. 在 PCB 编辑器中，点击顶部菜单的 **导出至FreeCAD**
2. 选择 **连接FreeCAD**（确保 FreeCAD 服务器已启动）
3. 连接成功后，选择 **导出到FreeCAD**
4. PCB 模型会自动发送到 FreeCAD 并导入

## 菜单功能

| 菜单选项       | 功能说明                      |
| ---------- | ------------------------- |
| 连接FreeCAD  | 连接到 FreeCAD WebSocket 服务器 |
| 导出到FreeCAD | 将 PCB STEP 文件发送到 FreeCAD  |
| 检查连接状态     | 查看当前与 FreeCAD 的连接状态       |
| 断开连接       | 断开与 FreeCAD 的连接           |

## 技术说明

- **通信方式**：WebSocket
- **WebSocket 端口**：8766
- **文件格式**：STEP (.step)
- **FreeCAD 版本要求**：1.0 或更高

## 常见问题

**Q: 连接 FreeCAD 失败？**

A: 请确保：

1. FreeCAD 已启动且 WebSocket 服务器脚本已运行
2. 端口 8766 未被占用
3. 嘉立创EDA扩展已开启外部交互权限

**Q: 需要安装额外依赖吗？**

A: 脚本首次运行时会自动安装 `websockets` 库。如果自动安装失败，可手动执行：

```shell
"<FreeCAD安装目录>/bin/python.exe" -m pip install websockets==13.1
```

**Q: 导入后 FreeCAD 没有反应？**

A: 请确保在 FreeCAD 中打开了 **视图 → 面板 → 报告视图**，查看是否有错误日志。

## 开源许可

本扩展使用 [Apache License 2.0](https://choosealicense.com/licenses/apache-2.0/) 开源许可协议。
