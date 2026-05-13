# 从零实现嘉立创 EDA 与 FreeCAD 的 PCB 双向实时协同

> 基于 WebSocket + STEP 的轻量级 MCAD-ECAD 协同方案，实现 PCB 元件在 EDA 与 FreeCAD 之间的双向定位、位置同步和实时交互。

## 背景

在 PCB 设计流程中，硬件工程师（EE）和结构工程师（ME）之间的协同一直是个痛点。EE 在 EDA 工具（如嘉立创 EDA 专业版）中完成电路和 PCB 布局，ME 在 MCAD 工具（如 FreeCAD / SolidWorks）中进行结构设计和装配检查。两者的数据格式、坐标系、操作习惯完全不��。

典型的工作流是：EE 导出 STEP 文件 → ME 手动导入 → 检查干涉 → 反馈问题 → EE 修改 → 重新导出……循环往复。**一次干涉检查可能要等半小时**。

能不能让两边的操作实时同步？在 EDA 里拖动一个电阻，FreeCAD 里的 3D 模型立刻跟着动；在 FreeCAD 里点击一个元件，EDA 自动定位到它？

这就是本项目要解决的问题。

## 架构总览

```
┌─────────────────────┐              ┌──────────────────────┐
│   嘉立创 EDA 专业版   │   WebSocket  │   FreeCAD + Python    │
│                     │◄────────────►│   WebSocket Server    │
│  TypeScript 扩展     │  ws://8766   │                      │
│  - 分片上传 STEP    │              │  - 分片接收 & 重组      │
│  - 事件监听          │              │  - STEP 导入 & 居中    │
│  - 位置同步          │              │  - 导入心跳保活        │
│  - 交叉定位          │              │  - 元件映射            │
│                     │              │  - 位置监听 (QTimer)   │
└─────────────────────┘              └──────────────────────┘
```

**技术选型思路：**

- **WebSocket**：双向实时通信，延迟低，EDS 扩展 API 原生支持
- **STEP 格式**：PCB 3D 模型的行业标准格式，FreeCAD 原生支持导入
- **TypeScript 扩展**：嘉立创 EDA 专业版的扩展开发语言
- **Python 宏**：FreeCAD 内置 Python 环境，可直接操作 3D 对象

## 核心功能

| 功能 | 方向 | 说明 |
|------|------|------|
| 分片上传 STEP | EDA → FreeCAD | 512KB 分片 Base64 传输，支持大文件 |
| 位置同步 | EDA ↔ FreeCAD | 移动元件，对面实时跟随 |
| 交叉定位 | EDA ↔ FreeCAD | 点击元件，对面自动聚焦 |
| 删除同步 | EDA → FreeCAD | EDA 删除元件，FreeCAD 同步移除 |
| 位号重命名 | EDA → FreeCAD | 改名后映射自动更新 |
| 导入心跳保活 | FreeCAD → EDA | 导入期间每 2 秒发送进度，防止超时 |

菜单结构：

```
FreeCAD机电协同
├── 导出3D到FreeCAD      ← 全量导出
├── 启用双向交互          ← 开启实时同步
├── 停止双向交互          ← 关闭同步
├── 连接FreeCAD
└── 断开FreeCAD
```

## 技术实现详解

### 1. STEP 文件分片传输与导入

EDA 的 `pcb_ManufactureData.get3DFile()` API 可以生成包含元件 3D 模型、丝印、铜线的 STEP 文件。

**为什么不能直接发？** 早期版本将整个文件用 `Array.from(new Uint8Array(buffer))` 编码成 JSON 一次性发送。每个字节变成一个十进制数字加逗号，20MB 的 STEP 文件膨胀为约 80MB 的 JSON 字符串。超过服务端 100MB 的 WebSocket 帧限制就直接断连。即使不超限，巨大的单条消息也会阻塞事件循环导致超时。

**解决方案：分片 Base64 传输。** 将文件按 512KB 切片，每片 Base64 编码后单独发送（仅 33% 体积膨胀，远低于原来的 300%）：

```typescript
const CHUNK_SIZE = 512 * 1024;  // 512KB per chunk

async function sendFileChunked(buffer: ArrayBuffer, filename: string) {
  const sessionId = Date.now().toString(36) + Math.random().toString(36).substring(2);
  const totalSize = buffer.byteLength;
  const totalChunks = Math.ceil(totalSize / CHUNK_SIZE);

  // 1. 通知服务端开始上传
  sendToFreeCAD({ type: 'file_upload_start', sessionId, filename, totalSize, totalChunks });

  // 2. 逐片发送（不等待单条 ACK，连续发送）
  for (let i = 0; i < totalChunks; i++) {
    const chunk = buffer.slice(i * CHUNK_SIZE, Math.min((i + 1) * CHUNK_SIZE, totalSize));
    const base64Data = arrayBufferToBase64(chunk);
    sendToFreeCAD({ type: 'file_upload_chunk', sessionId, index: i, data: base64Data });
  }
}
```

FreeCAD 端为每个上传会话维护一个 `ChunkedUploadSession`，逐片 Base64 解码并写入临时文件：

```python
class ChunkedUploadSession:
    def __init__(self, session_id, filename, total_size, total_chunks, temp_dir):
        self.file_handle = open(os.path.join(temp_dir, filename), 'wb')
        self.received_chunks = 0
        self.total_chunks = total_chunks

    def write_chunk(self, index, chunk_data):
        self.file_handle.write(chunk_data)  # 顺序写入
        self.received_chunks += 1

async def handle_upload_chunk(self, websocket, data):
    session = self.active_uploads.get(data['sessionId'])
    chunk_bytes = base64.b64decode(data['data'])
    session.write_chunk(data['index'], chunk_bytes)

    if session.received_chunks >= session.total_chunks:
        session.finish()  # 关闭文件句柄
        self.message_queue.put({'type': 'import_step', ...})  # 交给主线程导入
```

全部分片收完后，由主线程通过 `ImportGui.open()` 导入：

```python
def import_step_file(self, file_path):
    import ImportGui
    ImportGui.open(file_path)         # 首次导入，创建新文档
    doc = FreeCAD.ActiveDocument
    self.center_model(doc)            # 居中到原点
    FreeCADGui.SendMsgToActiveView("ViewFit")
```

### 2. 异步导入心跳保活

大文件 STEP 导入时，`ImportGui.open()` 在 FreeCAD 主线程中同步执行，可能阻塞数十秒到数分钟。虽然 WebSocket 运行在独立线程不受影响，但客户端长时间收不到消息会误判为断连。

解决方案是启动一个 **后台心跳线程**，在主线程被阻塞期间通过 asyncio 事件循环持续发送进度：

```python
def process_message_queue(self):
    if msg_type == 'import_step':
        self.import_in_progress = True
        self.import_start_time = time.time()

        # 通知客户端导入开始
        self.send_to_clients({"type": "import_started", ...})

        # 启动心跳线程（独立于主线程，不受 ImportGui 阻塞影响）
        threading.Thread(target=self._import_heartbeat, args=(session_id,), daemon=True).start()

        success = self.import_step_file(msg['file_path'])  # 阻塞主线程
        self.import_in_progress = False

def _import_heartbeat(self, session_id):
    while self.import_in_progress:
        elapsed = int((time.time() - self.import_start_time) * 1000)
        self.send_to_clients({"type": "import_progress", "sessionId": session_id, "elapsed_ms": elapsed})
        time.sleep(2)  # 每 2 秒一次
```

关键点：`send_to_clients()` 内部用 `asyncio.run_coroutine_threadsafe()` 提交到 asyncio 事件循环，**不依赖主线程**。所以即使 ImportGui 阻塞了整个 Qt 事件循环，心跳消息仍然能正常发送。

### 3. 模型居中与坐标补偿

STEP 文件导入后，模型中心通常不在原点。为方便查看，我们将所有对象平移到原点：

```python
def center_model(self, doc):
    # 计算包围盒中心
    cx, cy, cz = bounding_box_center(doc.Objects)
    self.center_offset = {'x': cx, 'y': cy, 'z': cz}

    # 所有对象平移 (-cx, -cy, -cz)
    for obj in doc.Objects:
        p = obj.Placement
        new_base = FreeCAD.Vector(p.Base.x - cx, p.Base.y - cy, p.Base.z - cz)
        obj.Placement = FreeCAD.Placement(new_base, p.Rotation)
```

**关键细节：** 居中偏移量必须记录下来，后续的位置同步都需要补偿这个偏移。这是最容易遗漏的地方——**EDA 发送的是原始坐标，FreeCAD 对象已被偏移，两边对不上的 bug 会非常隐蔽**。

### 4. 元件映射——三轮匹配策略

双向交互的前提是建立 EDA 位号（如 "R5"）和 FreeCAD 对象 Label（如 "R5~R0402XX"）之间的映射关系。我们设计了三轮渐进式匹配：

```
第一轮：精确匹配     "R5" == "R5"           → 直接命中
第二轮：单词边界匹配  "R5" ~in~ "R5~R0402"   → 不匹配 "R50"
第三轮：位置匹配     坐标距离 < 2mm          → 兜底策略
```

**第二轮的单词边界匹配是最关键的**，需要防止 `R1` 错误匹配到 `R10`、`R11` 等：

```python
# 错误做法：子串匹配 "R1" in "R10" == True，会导致 R1 吃掉 R10 的对象
if desig_upper in label_upper:  # BUG!

# 正确做法：正则边界匹配
# (?<![A-Za-z0-9]) 前面不能是字母数字
# (?![0-9]) 后面不能是数字（防止 R1 匹配 R10）
pattern = re.compile(
    r'(?<![A-Za-z0-9])' + re.escape(designator) + r'(?![0-9])',
    re.IGNORECASE
)
if pattern.search(fc_obj['label']):  # R5 匹配 "R5~R0402XX"，不匹配 "R50"
```

**第三轮位置匹配要注意坐标系统的一致性：**

```python
# EDA 已经把 mil 转为 mm 发过来了，不要再乘 0.0254（双重转换 bug！）
eda_x_mm = comp.get('x', 0)  # 正确：直接用 mm
eda_y_mm = comp.get('y', 0)

# FreeCAD 对象被居中偏移过，要加回偏移才能和 EDA 原始坐标比较
fc_real_x = fc_obj['x'] + self.center_offset['x']
fc_real_y = fc_obj['y'] + self.center_offset['y']
dist = math.hypot(fc_real_x - eda_x_mm, fc_real_y - eda_y_mm)
```

### 5. 对象分组——防止"牵一发动全身"

STEP 导入后，一个元件可能对应多个 FreeCAD 对象（3D 模型、丝印文字、焊盘铜箔等）。移动时这些对象需要一起动。

分组策略：同一位置（0.5mm 容差内）的非主对象归入该元件的组：

```python
main_labels = set(self.designator_map.values())  # 所有元件的主对象
for designator, main_label in self.designator_map.items():
    group = [main_label]
    for obj in freecad_objects:
        if obj['label'] == main_label: continue
        if obj['label'] in main_labels: continue  # 不抢其他元件的主对象！
        if distance(obj, main_obj) < 0.5:
            group.append(obj['label'])
    self.designator_groups[designator] = group
```

**曾经踩过的坑：** 早期版本没有排除其他元件的主对象，且容差设为 1mm。结果是移动一个电阻时，64 个对象全部偏移到坐标 (9999, 9999) 的位置——所有元件都被错误地归入了同一个组。

### 6. 双向位置同步

这是整个系统最核心也最容易出 bug 的部分。需要解决三个关键问题：

#### 6.1 坐标单位转换

EDA 使用 **mil（密尔）**，FreeCAD 使用 **mm（毫米）**：

```typescript
// EDA → FreeCAD（TypeScript）
const MIL_TO_MM = 0.0254;
const MM_TO_MIL = 1 / 0.0254;

// 读取 EDA 坐标并转为 mm
const x_mm = comp.getState_X() * MIL_TO_MM;
const y_mm = comp.getState_Y() * MIL_TO_MM;

// FreeCAD → EDA
comp.setState_X(message.x * MM_TO_MIL);
comp.setState_Y(message.y * MM_TO_MIL);
```

#### 6.2 居中偏移补偿

```python
# EDA → FreeCAD：EDA 原始坐标减去偏移得到 FC 坐标
fc_x = eda_x - self.center_offset['x']
fc_y = eda_y - self.center_offset['y']

# FreeCAD → EDA：FC 坐标加上偏移还原为 EDA 坐标
eda_x = fc_x + self.center_offset['x']
eda_y = fc_y + self.center_offset['y']
```

#### 6.3 防循环更新

EDA 改了位置 → 通知 FreeCAD → FreeCAD 位置变了 → 又通知 EDA → 无限循环……

解决方案：用 `last_update_source` 标记更新来源：

```python
def do_position_update(self, designator, x, y, rotation):
    self.last_update_source = 'eda'   # 标记来源
    # ... 更新 FreeCAD 对象位置 ...
    self.last_update_source = None    # 清除标记

def check_position_changes(self):
    if self.last_update_source is not None:
        return  # 来源是 EDA，不回传，防止循环
```

### 7. 交���定位

点击 EDA 中的元件，FreeCAD 自动选中并聚焦；反之亦然。

**EDA → FreeCAD：**

```typescript
// 监听鼠标选中事件
eda.pcb_Event.addMouseEventListener(MOUSE_ID, 'selected', onPcbMouseSelect);

function onPcbMouseSelect(eventType, props) {
    const designator = props[0].parentComponentDesignator || props[0].designator;
    sendToFreeCAD({ type: 'cross_probe', designator });
}
```

```python
# FreeCAD 端选中对象
def do_cross_probe(self, designator):
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(obj)
    FreeCADGui.SendMsgToActiveView("ViewFit")
```

**FreeCAD → EDA：**

```python
# 检测到位置变化时发送交叉定位消息
self.send_to_clients({
    "type": "cross_probe_from_freecad",
    "designator": designator,
    "x": eda_x, "y": eda_y
})
```

```typescript
// EDA 端执行交叉定位
await eda.pcb_SelectControl.doCrossProbeSelect([designator], undefined, undefined, true, true);
await eda.pcb_Document.navigateToCoordinates(x * MM_TO_MIL, y * MM_TO_MIL);
```

### 8. 线程安全——QTimer + 消息队列

这是 FreeCAD 扩展开发中最容易被忽视的问题。

**FreeCAD 的 GUI 操作（修改 Placement、添加/删除对象等）必须在主线程执行。** 但 WebSocket 的消息回调运行在独立线程。直接在回调中操作 FreeCAD 对象会导致崩溃或无效操作。

解决方案是经典的 **消息队列 + 主线程轮询** 模式：

```python
import queue
from PySide2.QtCore import QTimer

class WebSocketPCBServer:
    def __init__(self):
        self.message_queue = queue.Queue()  # 线程安全队列

    # WebSocket 线程：收到消息后放入队列
    async def handle_message(self, websocket, message):
        data = json.loads(message)
        self.message_queue.put({'type': 'position_update', ...})

    # 主线程：QTimer 每 100ms 轮询队列，安全执行 FreeCAD 操作
    def process_message_queue(self):
        messages = self.message_queue.get_all()
        for msg in messages:
            if msg['type'] == 'position_update':
                self.do_position_update(...)  # 主线程安全操作

# 启动时注册定时器
timer = QTimer()
timer.timeout.connect(server.process_message_queue)
timer.start(100)  # 100ms 轮询
```

架构示意：

```
WebSocket 线程              主线程（FreeCAD GUI）
     │                            │
 收到消息 ──► queue ──► QTimer 轮询 ──► 执行操作
     │         (线程安全)         (100ms)
     │                            │
     │                     修改 Placement ✓
     │                     删除对象 ✓
     │                     选中对象 ✓
```

### 9. 心跳检测

EDA 的 WebSocket API 有一个特性：连接断开后 `send()` **不会立即抛错**。需要心跳机制来检测真实连接状态：

```typescript
const HEARTBEAT_INTERVAL_MS = 3000;  // 每 3 秒发 ping
const HEARTBEAT_TIMEOUT_MS = 8000;   // 8 秒无 pong 视为断连

function startHeartbeat() {
    lastPongTime = Date.now();
    heartbeatTimer = setInterval(() => {
        if (Date.now() - lastPongTime > HEARTBEAT_TIMEOUT_MS) {
            onConnectionLost();  // 自动断开、清理状态
            return;
        }
        sendToFreeCAD({ type: 'ping' });
    }, HEARTBEAT_INTERVAL_MS);
}
```

## 踩坑实录

### 踩坑 1：事件类型不是 "move" 而是 "modify"

嘉立创 EDA 的事件类型文档写的是 `move`，但实际拖动元件时触发的是 `modify`。必须同时监听两者：

```typescript
if (eventType === 'move' || eventType === 'modify') {
    syncPositionToFreecad(...);
}
```

### 踩坑 2：事件 props 里 designator 全是 undefined

移动元件时，事件触发的是子图元（焊盘、丝印等），而不是 Component 本身。子图元的 `designator` 和 `parentComponentDesignator` 都是空的。

解决方案：提前构建 `primitiveId → designator` 反查表，通过 `parentComponentPrimitiveId` 或 `primitiveId` 反查：

```typescript
// 启动时构建反查表
const components = await eda.pcb_PrimitiveComponent.getAll();
for (const comp of components) {
    primitiveIdToDesignator.set(comp.getState_PrimitiveId(), comp.getState_Designator());
}

// 事件回调中使用反查
const designator =
    prop.designator ||
    prop.parentComponentDesignator ||
    primitiveIdToDesignator.get(prop.primitiveId) ||
    primitiveIdToDesignator.get(prop.parentComponentPrimitiveId);
```

### 踩坑 3：`modify()` 方法不存在

嘉立创 EDA 的 `IPCB_PrimitiveComponent` 没有 `modify()` 方法。修改元件必须用 `setState_*` 系列 + `done()`：

```typescript
// 错误：comp.modify({ x: newX, y: newY })
// 正确：
comp.setState_X(newX);
comp.setState_Y(newY);
comp.setState_Rotation(newRot);
await comp.done();  // 必须调用 done() 提交！
```

### 踩坑 4：FreeCAD Rotation 没有 `getRaw()` 方法

FreeCAD 的 Rotation 对象在不同版本之间 API 不一致。`getRaw()` 在某些版本不存在。正确的方式是用 `getYawPitchRoll()`：

```python
# 错误：rotation.getRaw()  → AttributeError
# 正确：
yaw, pitch, roll = obj.Placement.Rotation.getYawPitchRoll()
```

### 踩坑 5：FreeCAD Selection API

选中对象的正确方式是通过 `FreeCADGui.Selection`，不是通过 document 对象：

```python
# 错误：gui_doc.clearSelection()  → AttributeError
# 正确：
FreeCADGui.Selection.clearSelection()
FreeCADGui.Selection.addSelection(obj)
```

### 踩坑 6：子串匹配导致所有元件被错误分组

`"R1" in "R10"` 的结果是 `True`。这导致 R1 的映射把 R10、R11、R12……的对象全部吞走。移动 R1 时，这些元件全部偏移到错误位置。

修复：使用正则的负向前瞻 `(?![0-9])` 确保后面不跟数字。

### 踩坑 7：位置匹配的双重单位转换

EDA 已经将 mil 转为 mm 发送，但 FreeCAD 端又乘了一次 0.0254。结果坐标缩小了 40 倍，位置匹配完全失效。加上居中偏移未补偿，第三轮匹配形同虚设。

## 完整交互流程

以"启用双向交互"为例，完整的数据流：

```
用户点击「启用双向交互」
    │
    ▼
┌─ 检查 WebSocket 连接，未连接则自动连接
│
├─ 获取所有元件 → 构建 designator↔primitiveId 映射表
│
├─ 注册事件监听
│   ├─ addPrimitiveEventListener('all', onPcbPrimitiveChange)
│   └─ addMouseEventListener('selected', onPcbMouseSelect)
│
├─ 全量导出 STEP → FreeCAD 导入 → 居中
│
├─ 发送 build_mapping → FreeCAD 三轮匹配 → 返回映射结果
│
├─ 发送 enable_monitor → FreeCAD 启动位置监听
│
└─ Toast: "双向交互已启动"
     │
     ▼
  ┌─────────────────────────────────────────┐
  │          实时双向同步循环                    │
  │                                         │
  │  EDA 拖动元件 → position_update → FC 移动  │
  │  FC 拖动对象 → QTimer 检测 → EDA 移动      │
  │  EDA 点击元件 → cross_probe → FC 聚焦     │
  │  EDA 删除元件 → delete_object → FC 删除    │
  │  EDA 改位号   → rename_designator → FC 更名│
  └─────────────────────────────────────────┘
```

## WebSocket 消息协议

| 方向 | type | 数据字段 | 说明 |
|------|------|---------|------|
| EDA→FC | `file_upload_start` | sessionId, filename, totalSize, totalChunks | 分片上传开始 |
| EDA→FC | `file_upload_chunk` | sessionId, index, data(base64) | 单个分片数据 |
| FC→EDA | `upload_started` | sessionId | 服务端确认接收上传 |
| FC→EDA | `chunk_received` | sessionId, index, received, total | 分片确认+进度 |
| FC→EDA | `upload_complete` | sessionId, message | 全部分片接收完成 |
| FC→EDA | `import_started` | sessionId | 开始导入 STEP |
| FC→EDA | `import_progress` | sessionId, elapsed_ms | 导入进行中心跳 |
| FC→EDA | `import_complete` | sessionId, details | 导入完成 |
| EDA→FC | `build_mapping` | components[{designator,x,y,rotation}] | 请求建立映射 |
| FC→EDA | `mapping_result` | mapping[{designator,freecadLabel}] | 返回映射结果 |
| EDA→FC | `position_update` | designator, x, y, rotation | EDA 元件移动 |
| FC→EDA | `position_update_from_freecad` | designator, x, y, rotation | FreeCAD 对象移动 |
| EDA→FC | `delete_object` | designator | EDA 元件删除 |
| EDA→FC | `cross_probe` | designator | EDA→FC 交叉定位 |
| FC→EDA | `cross_probe_from_freecad` | designator, x, y | FC→EDA 交叉定位 |
| EDA→FC | `rename_designator` | old, new | 位号重命名 |
| EDA→FC | `enable_monitor` | (空) | 启动 FC 端位置监听 |
| EDA→FC | `disable_monitor` | (空) | 停止 FC 端位置监听 |
| 双向 | `ping` / `pong` | (空) | 心跳 |

## 已知限制

1. **Board 复合体是"幽灵"**：STEP 文件中 board、topcopper、topsilkscreen 是包含所有元件形状的复合几何体。移动某个元件后，这些复合体中该元件的旧位置仍然可见（"幽灵残影"）。这是 STEP 几何的限制，无法通过修改 Placement 消除。需要编辑完成后重新全量导出。

2. **位置监听有 500ms 延迟**：FreeCAD 没有原生的对象属性变化回调，只能用 QTimer 轮询。对于快速拖拽，FreeCAD→EDA 方向会有轻微延迟。

3. **STEP 不保留元件层级**：STEP 是纯几何格式，不包含元件的层级关系（哪个面属于哪个元件）。匹配完全依赖 Label 文本和位置距离。

4. **大文件导入耗时取决于硬件**：STEP 导入使用 FreeCAD 的 OpenCASCADE 内核（单线程），80 个对象的 PCB 通常需要数分钟。导入期间 FreeCAD GUI 会无响应，但后台心跳线程会持续向 EDA 客户端发送进度保活。CPU 单核性能和内存大小是主要影响因素。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| EDA 扩展 | TypeScript | 嘉立创 EDA 专业版扩展 |
| 通信协议 | WebSocket (JSON) | 双向实时通信 |
| 3D 格式 | STEP | PCB 3D 模型导出 |
| FreeCAD 脚本 | Python | WebSocket 服务器 + 3D 操作 |
| 线程同步 | QTimer + Queue | 主线程安全的 FreeCAD 操作 |
| 国际化 | JSON i18n | 中英双语 |

## 项目结构

```
pcb-export-to-freeCad/
├── src/
│   └── index.ts                         # EDA 扩展主逻辑
├── script/
│   ├── Interactive-with-easyeda.py      # FreeCAD WebSocket 服务器
│   └── eda_api_reference.md             # EDA API 参考手册
├── locales/
│   ├── zh-Hans.json                     # 中文翻译
│   └── en.json                          # 英文翻译
├── extension.json                       # 扩展配置
└── dist/                                # 构建输出
```

## 写在最后

这个项目的核心价值不在于代码量（总共不到 1500 行），而在于打通了 EDA 和 MCAD 之间的实时数据通道。在 PCB 设计中，"结构干涉检查"从原本的"导出-导入-检查-反馈"循环，变成了"拖一下看看"的即时体验。

项目已开源（Apache 2.0），欢迎使用和改进。如果你在做类似的 ECAD-MCAD 协同工作，欢迎交流。

---

*如果觉得有用，欢迎点赞收藏。有问题欢迎评论区讨论。*
