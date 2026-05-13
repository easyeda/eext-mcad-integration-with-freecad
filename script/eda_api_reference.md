# EDA 扩展开发 API 参考手册

> 本项目使用的嘉立创 EDA (EasyEDA Pro) 扩展接口整理，基于实际开发调试验证。

***

## 一、消息提示 `eda.sys_Message`

### `showToastMessage(message, type)`

显示一条 Toast 提示消息。

| 参数      | 类型     | 说明                                  |
| ------- | ------ | ----------------------------------- |
| message | string | 提示文本内容                              |
| type    | 枚举     | 消息类型，可选值见下方 `ESYS_ToastMessageType` |

**消息类型枚举** **`ESYS_ToastMessageType`：**

| 值         | 说明 |
| --------- | -- |
| `SUCCESS` | 成功 |
| `INFO`    | 信息 |
| `WARNING` | 警告 |
| `ERROR`   | 错误 |

**示例：**

```typescript
eda.sys_Message.showToastMessage('操作成功', ESYS_ToastMessageType.SUCCESS);
```

***

## 二、国际化 `eda.sys_I18n`

### `text(key, arg2?, arg3?, ...params)`

获取国际化文本，支持模板参数替换。

| 参数        | 类型     | 说明                               |
| --------- | ------ | -------------------------------- |
| key       | string | 要显示的文本，也是翻译的 key。如果找不到翻译会原样返回    |
| arg2      | any    | （可选）未使用，传 `undefined`            |
| arg3      | any    | （可选）未使用，传 `undefined`            |
| ...params | any\[] | 模板参数，用于替换文本中的 `${1}`、`${2}` 等占位符 |

**⚠️ 重要特性：** i18n 系统做**子串匹配**。独立的短 key 会匹配并覆盖包含它的组合 key。例如同时存在 `"处理中"` 和 `"处理中 ${1}%"` 时，`text("处理中 ${1}%")` 可能被短 key `"处理中"` 截获。应避免定义会被子串匹配的独立 key。

**模板语法：** 使用 `${1}`、`${2}` 按序号引用 params 参数。

**示例：**

```typescript
// 无参数
eda.sys_I18n.text('正在连接到FreeCAD服务器...');

// 带模板参数
eda.sys_I18n.text('导出失败: ${1}', undefined, undefined, errorMsg);
// => "导出失败: 连接超时"
```

***

## 三、对话框 `eda.sys_Dialog`

### `showInformationMessage(message, title?)`

弹出信息对话框。

| 参数      | 类型     | 说明    |
| ------- | ------ | ----- |
| message | string | 对话框内容 |
| title   | string | 对话框标题 |

***

## 四、持久化存储 `eda.sys_Storage`

### `getExtensionUserConfig(key)` / `setExtensionUserConfig(key, value)`

读写扩展的用户配置数据（跨会话持久化）。

**读取返回值：** `any` — 不存在时返回 `undefined`。

***

## 五、WebSocket 通信 `eda.sys_WebSocket`

### `register(id, url, onMessage, onConnected?)`

注册并连接一个 WebSocket 服务。

| 参数          | 类型       | 说明                                      |
| ----------- | -------- | --------------------------------------- |
| id          | string   | WebSocket 连接的唯一标识符                      |
| url         | string   | WebSocket 服务器地址，如 `ws://localhost:8766` |
| onMessage   | function | 接收消息的回调函数，参数为 `MessageEvent`            |
| onConnected | function | （可选）连接成功后的回调函数                          |

### `send(id, data)` / `close(id, code, reason)`

发送数据或关闭连接。

| 参数 | 类型 | 说明 |
| ---- | ---- | ---- |
| id | string | WebSocket 连接标识符 |
| data | string \| ArrayBuffer \| ArrayBufferView | 要发送的数据（字符串会被作为文本帧发送） |
| code | number | 关闭状态码，如 `1000` 表示正常关闭 |
| reason | string | 关闭原因描述 |

**⚠️ 注意：** `send()` 在连接已断开时**不会立即抛错**，需靠心跳机制检测断连。

**⚠️ 大文件传输：** `send()` 发送的是完整 WebSocket 帧。大体积 JSON 会阻塞事件循环并可能超出对端 `max_size` 限制。对于文件传输，应使用 **分片 Base64 编码**（见踩坑记录 #6）。

***

## 六、PCB 制造数据 `eda.pcb_ManufactureData`

### `get3DFile(typeName, format, layers, subfolder?)` → `Promise<File>`

本项目参数：`('pcbModel', 'step', ['Component Model', 'Silkscreen', 'Wire In Signal Layer'], 'Parts')`

返回的 File 对象可用 `FileReader.readAsArrayBuffer()` 读取。

**读取模式：**

```typescript
const pcbFile = await eda.pcb_ManufactureData.get3DFile('pcbModel', 'step', [...], 'Parts');
if (!pcbFile) throw new Error('无法获取文件');

const arrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
        if (reader.result instanceof ArrayBuffer) resolve(reader.result);
        else reject(new Error('FileReader返回的不是ArrayBuffer'));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(pcbFile);
});

// arrayBuffer.byteLength 即文件大小（bytes）
```

**⚠️ 大文件处理：** PCB 的 STEP 文件可能超过 20MB。不要用 `Array.from(new Uint8Array(buffer))` 编码成 JSON（体积膨胀约 300%），应使用 **分片 Base64 传输**（见踩坑记录 #6）。

***

## 七、PCB 元件操作 `eda.pcb_PrimitiveComponent`

### `getAll(layer?, lock?)` → `Promise<Array<IPCB_PrimitiveComponent>>`

获取所有元件。返回的每个对象包含以下方法：

### 元件状态读取方法

| 方法                       | 返回类型               | 说明     |
| ------------------------ | ------------------ | ------ |
| `getState_Designator()`  | `string \| undefined` | 位号     |
| `getState_PrimitiveId()` | `string`           | 图元 ID  |
| `getState_X()`           | `number`           | X 坐标（**单位: mil**） |
| `getState_Y()`           | `number`           | Y 坐标（**单位: mil**） |
| `getState_Rotation()`    | `number`           | 旋转角度   |
| `getState_Layer()`       | `TPCB_LayersOfComponent` | 层      |
| `getState_Footprint()`   | `{libraryUuid, uuid, name?} \| undefined` | 关联封装   |
| `getState_PrimitiveType()` | `EPCB_PrimitiveType` | 图元类型   |

**⚠️ 坐标单位：** `getState_X()` / `getState_Y()` 返回的是 **mil（密尔）**，不是 mm。
转换公式：`mm = mil × 0.0254`，`mil = mm × 39.3701`

### `get(primitiveId)` → `Promise<IPCB_PrimitiveComponent | undefined>`

通过 primitiveId 获取单个元件。

### 元件状态修改方法

| 方法                       | 返回类型                        | 说明     |
| ------------------------ | --------------------------- | ------ |
| `setState_X(x)`          | `IPCB_PrimitiveComponent`   | 设置 X 坐标（**mil**） |
| `setState_Y(y)`          | `IPCB_PrimitiveComponent`   | 设置 Y 坐标（**mil**） |
| `setState_Rotation(rot)` | `IPCB_PrimitiveComponent`   | 设置旋转角度 |
| `setState_Designator(d)` | `IPCB_PrimitiveComponent`   | 设置位号   |

**⚠️ 修改后必须调用 `done()` 提交更改：**

```typescript
const comp = await eda.pcb_PrimitiveComponent.get(primitiveId);
comp.setState_X(newX);      // mil
comp.setState_Y(newY);      // mil
comp.setState_Rotation(rot);
await comp.done();           // 提交到画布
```

**⚠️ `IPCB_PrimitiveComponent` 没有 `modify()` 方法！** 只能通过 `setState_*` + `done()` 修改。

### `delete(primitiveIds)` → `Promise<boolean>`

删除元件。参数可以是 string、对象或数组。

***

## 八、PCB 事件系统 `eda.pcb_Event`

### `addPrimitiveEventListener(id, eventType, callFn, onlyOnce?)`

监听图元事件。

| 参数        | 类型     | 说明                                    |
| --------- | ------ | ------------------------------------- |
| id        | string | 唯一标识符，防止重复注册                          |
| eventType | string | `'all'` 或具体类型                          |
| callFn    | function | 回调函数                                  |
| onlyOnce  | boolean | （可选）是否只监听一次                           |

**回调签名：**

```typescript
(eventType: string, props: Array<{
    primitiveId: string;
    primitiveType: EPCB_PrimitiveType;
    net?: string;
    designator?: string;
    parentComponentPrimitiveId?: string;
    parentComponentDesignator?: string;
}>) => void | Promise<void>
```

**图元事件类型 `EPCB_PrimitiveEventType`：**

| 值         | 说明   |
| --------- | ---- |
| `"create"`  | 创建   |
| `"delete"`  | 删除   |
| `"change"`  | 属性变更 |
| `"move"`    | 移动   |

**⚠️ 实测发现拖动元件触发的是 `"modify"` 而非 `"move"`！** 建议同时监听两者：
```typescript
if (eventType === 'move' || eventType === 'modify') { /* 同步位置 */ }
```

**⚠️ props 中的 `designator` 和 `parentComponentDesignator` 可能为空。** 移动操作触发的是子图元（焊盘等），不是 Component 本身。需要通过 `primitiveId` 或 `parentComponentPrimitiveId` 反查 designator。

### `addMouseEventListener(id, eventType, callFn, onlyOnce?)`

监听鼠标事件。

**回调签名：**

```typescript
(eventType: EPCB_MouseEventType, props: Array<{
    primitiveId: string;
    primitiveType: EPCB_PrimitiveType;
    net?: string;
    designator?: string;
    parentComponentPrimitiveId?: string;
    parentComponentDesignator?: string;
}>) => void | Promise<void>
```

**鼠标事件类型 `EPCB_MouseEventType`：**

| 值                | 说明   |
| ---------------- | ---- |
| `"selected"`     | 选中   |
| `"clearSelected"` | 取消选中 |

### `addCrossProbeSelectEventListener(id, callFn)` （BETA）

监听交叉选择事件。

### `removeEventListener(id)` → `boolean`

移除事件监听。

### `isEventListenerAlreadyExist(id)` → `boolean`

查询事件监听是否存在。

***

## 九、PCB 选择控制 `eda.pcb_SelectControl`

### `doCrossProbeSelect(components?, pins?, nets?, highlight?, select?)` → `Promise<boolean>`

交叉选择/定位。

| 参数         | 类型         | 说明                    |
| ---------- | ---------- | --------------------- |
| components | `string[]` | 器件位号列表，如 `['R1', 'C1']` |
| pins       | `string[]` | 引脚，格式 `'U1_1'`         |
| nets       | `string[]` | 网络名称                  |
| highlight  | `boolean`  | 是否高亮                  |
| select     | `boolean`  | 是否选中                  |

### `getAllSelectedPrimitives_PrimitiveId()` → `Promise<Array<string>>`

获取所有已选中图元的 ID。

### `getAllSelectedPrimitives()` → `Promise<Array<IPCB_Primitive>>`

获取所有已选中图元的对象。

### `clearSelected()` → `Promise<boolean>`

清除选中。

### `doSelectPrimitives(ids)` → `Promise<boolean>`

通过 ID 选中图元。

***

## 十、PCB 文档导航 `eda.pcb_Document`

### `navigateToCoordinates(x, y)` → `Promise<void>`

导航到指定坐标。**坐标单位是 mil。**

***

## 关键踩坑记录

### 1. 坐标单位

EDA PCB 坐标使用 **mil（密尔）**，FreeCAD 使用 **mm（毫米）**。

```typescript
const MIL_TO_MM = 0.0254;
const MM_TO_MIL = 1 / 0.0254; // ≈ 39.3701

// EDA → FreeCAD
const x_mm = comp.getState_X() * MIL_TO_MM;

// FreeCAD → EDA
const x_mil = fc_x * MM_TO_MIL;
comp.setState_X(x_mil);
```

### 2. 事件类型

- 拖动元件触发 `modify` 而非 `move`
- 事件 props 中 `designator` 和 `parentComponentDesignator` **可能为空**
- 需要通过 `primitiveId` 反查映射表获取 designator

### 3. i18n 子串匹配

独立的短 key（如 `"处理中"`）会覆盖包含它的组合 key（如 `"处理中 ${1}%"`）。应避免定义会被子串匹配的 key。

### 4. 组件修改

`IPCB_PrimitiveComponent` **没有** `modify()` 方法，必须用 `setState_X/Y/Rotation()` + `done()`。

### 5. 连接状态检测

`WebSocket.send()` 在连接断开后不会立即抛错。需要心跳机制（定时 ping/pong）检测真实连接状态。

### 6. `Array.from(new Uint8Array())` 导致大文件传输失败

将 ArrayBuffer 转为 JSON 数组发送时，每个字节变成一��十进制数字加逗号（如 `[72,101,108,...]`），体积膨胀约 **300%**。20MB 的 STEP 文件变成约 80MB 的 JSON 字符串，直接超出 WebSocket 帧限制导致断连。

**错误做法：**

```typescript
// 体积膨胀 ~300%，大文件必断
eda.sys_WebSocket.send(id, JSON.stringify({
    type: 'file_upload',
    data: Array.from(new Uint8Array(arrayBuffer))
}));
```

**正确做法：分片 Base64 传输**

```typescript
const CHUNK_SIZE = 512 * 1024; // 512KB per chunk

function arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 8192; // 分块转换避免 callstack 溢出
    let binary = '';
    for (let i = 0; i < bytes.length; i += chunkSize) {
        const slice = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
        binary += String.fromCharCode.apply(null, slice);
    }
    return btoa(binary);
}

// 分片发送，每片 Base64 后约 682KB，远低于任何限制
for (let i = 0; i < totalChunks; i++) {
    const chunk = buffer.slice(i * CHUNK_SIZE, Math.min((i + 1) * CHUNK_SIZE, totalSize));
    sendToFreeCAD({
        type: 'file_upload_chunk',
        index: i,
        data: arrayBufferToBase64(chunk),
    });
}
```

Base64 编码仅 **33% 体积膨胀**（vs 原来的 ~300%），且单条消息体积可控。

***

## 接口总览

| 模块                    | 方法                                | 用途                     |
| --------------------- | --------------------------------- | ---------------------- |
| `sys_Message`         | `showToastMessage`                | 显示 Toast 提示            |
| `sys_I18n`            | `text`                            | 获取国际化文本                |
| `sys_Dialog`          | `showInformationMessage`          | 弹出信息对话框                |
| `sys_Storage`         | `getExtensionUserConfig`          | 读取持久化配置                |
| `sys_Storage`         | `setExtensionUserConfig`          | 写入持久化配置                |
| `sys_WebSocket`       | `register` / `send` / `close`    | WebSocket 通信           |
| `pcb_ManufactureData` | `get3DFile`                       | 获取 PCB 3D STEP 模型文件    |
| `pcb_PrimitiveComponent` | `getAll` / `get`               | 获取元件                   |
| `pcb_PrimitiveComponent` | `setState_*` + `done()`        | 修改元件属性                 |
| `pcb_Event`           | `addPrimitiveEventListener`       | 监听图元事件（移动/删除/修改等）      |
| `pcb_Event`           | `addMouseEventListener`           | 监听鼠标事件（选中/取消选中）        |
| `pcb_Event`           | `removeEventListener`             | 移除事件监听                 |
| `pcb_SelectControl`   | `doCrossProbeSelect`              | 交叉选择定位                 |
| `pcb_SelectControl`   | `getAllSelectedPrimitives_PrimitiveId` | 获取选中图元 ID         |
| `pcb_Document`        | `navigateToCoordinates`           | 导航到坐标（mil）             |
