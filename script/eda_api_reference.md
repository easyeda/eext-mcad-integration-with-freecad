# EDA 扩展开发 API 参考手册

> 本项目使用的嘉立创 EDA 扩展接口整理，按模块分类。

---

## 一、消息提示 `eda.sys_Message`

### `showToastMessage(message, type)`

显示一条 Toast 提示消息。

| 参数   | 类型 | 说明                                       |
| ------ | ---- | ------------------------------------------ |
| message | string | 提示文本内容                               |
| type   | 枚举 | 消息类型，可选值见下方 `ESYS_ToastMessageType` |

**消息类型枚举 `ESYS_ToastMessageType`：**

| 值        | 说明   |
| --------- | ------ |
| `SUCCESS` | 成功   |
| `INFO`    | 信息   |
| `WARNING` | 警告   |
| `ERROR`   | 错误   |

**示例：**
```typescript
eda.sys_Message.showToastMessage('操作成功', ESYS_ToastMessageType.SUCCESS);
```

---

## 二、国际化 `eda.sys_I18n`

### `text(key, arg2?, arg3?, ...params)`

获取国际化文本，支持模板参数替换。

| 参数     | 类型     | 说明                                                         |
| -------- | -------- | ------------------------------------------------------------ |
| key      | string   | 要显示的文本，也是翻译的 key。如果找不到翻译会原样返回      |
| arg2     | any      | （可选）未使用，传 `undefined`                               |
| arg3     | any      | （可选）未使用，传 `undefined`                               |
| ...params | any[]   | 模板参数，用于替换文本中的 `${1}`、`${2}` 等占位符          |

**模板语法：** 使用 `${1}`、`${2}` 按序号引用 params 参数。

**示例：**
```typescript
// 无参数
eda.sys_I18n.text('正在连接到FreeCAD服务器...');

// 带模板参数
eda.sys_I18n.text('上传进度: ${1}% - ${2}', undefined, undefined, 50, '处理中');
// => "上传进度: 50% - 处理中"

eda.sys_I18n.text('导出失败: ${1}', undefined, undefined, errorMsg);
// => "导出失败: 连接超时"
```

---

## 三、对话框 `eda.sys_Dialog`

### `showInformationMessage(message, title?)`

弹出信息对话框。

| 参数    | 类型   | 说明       |
| ------- | ------ | ---------- |
| message | string | 对话框内容 |
| title   | string | 对话框标题 |

**示例：**
```typescript
eda.sys_Dialog.showInformationMessage(
    eda.sys_I18n.text('PCB FreeCAD 导出工具 v1.0.0'),
    eda.sys_I18n.text('About'),
);
```

---

## 四、持久化存储 `eda.sys_Storage`

### `getExtensionUserConfig(key)`

读取扩展的用户配置数据（跨会话持久化）。

| 参数 | 类型   | 说明        |
| ---- | ------ | ----------- |
| key  | string | 配置项的键名 |

**返回值：** `any` — 存储的值，不存在时返回 `undefined`。

### `setExtensionUserConfig(key, value)`

写入扩展的用户配置数据。

| 参数  | 类型   | 说明         |
| ----- | ------ | ------------ |
| key   | string | 配置项的键名 |
| value | any    | 要存储的值   |

**示例：**
```typescript
// 保存连接状态
eda.sys_Storage.setExtensionUserConfig('freecad_connected', true);

// 读取连接状态
const connected = eda.sys_Storage.getExtensionUserConfig('freecad_connected') === true;
```

---

## 五、WebSocket 通信 `eda.sys_WebSocket`

### `register(id, url, onMessage, onConnected?)`

注册并连接一个 WebSocket 服务。

| 参数        | 类型         | 说明                                          |
| ----------- | ------------ | --------------------------------------------- |
| id          | string       | WebSocket 连接的唯一标识符                    |
| url         | string       | WebSocket 服务器地址，如 `ws://localhost:8766` |
| onMessage   | function     | 接收消息的回调函数，参数为 `MessageEvent`     |
| onConnected | function     | （可选）连接成功后的回调函数                  |

### `send(id, data)`

通过已注册的 WebSocket 连接发送数据。

| 参数 | 类型   | 说明                     |
| ---- | ------ | ------------------------ |
| id   | string | WebSocket 连接的标识符   |
| data | string | 要发送的数据（JSON 字符串） |

### `close(id, code, reason)`

关闭已注册的 WebSocket 连接。

| 参数   | 类型   | 说明                   |
| ------ | ------ | ---------------------- |
| id     | string | WebSocket 连接的标识符 |
| code   | number | 关闭状态码（如 `1000` 表示正常关闭） |
| reason | string | 关闭原因描述           |

**示例：**
```typescript
// 注册连接
eda.sys_WebSocket.register(
    'freecad-pcb-exporter',
    'ws://localhost:8766',
    (event) => { console.log('收到消息:', event.data); },
    () => { console.log('已连接'); }
);

// 发送数据
eda.sys_WebSocket.send('freecad-pcb-exporter', JSON.stringify({ type: 'ping' }));

// 关闭连接
eda.sys_WebSocket.close('freecad-pcb-exporter', 1000, '用户主动断开');
```

---

## 六、PCB 制造数据 `eda.pcb_ManufactureData`

### `get3DFile(typeName, format, layers, subfolder?)`

获取 PCB 的 3D 模型文件。

| 参数      | 类型     | 说明                                                 |
| --------- | -------- | ---------------------------------------------------- |
| typeName  | string   | 模型类型名称，本项目使用 `'pcbModel'`                |
| format    | string   | 输出文件格式，如 `'step'`                            |
| layers    | string[] | 要包含的图层/元素列表                                |
| subfolder | string   | （可选）子文件夹名称                                 |

**本项目使用的参数：**
- `typeName`: `'pcbModel'`
- `format`: `'step'`
- `layers`: `['Component Model', 'Silkscreen', 'Wire In Signal Layer']`
- `subfolder`: `'Parts'`

**返回值：** `Promise<File>` — 包含 3D 模型数据的 File 对象，具有 `name`、`size` 属性，可用 `FileReader` 读取。

**示例：**
```typescript
const pcbFile = await eda.pcb_ManufactureData.get3DFile(
    'pcbModel',
    'step',
    ['Component Model', 'Silkscreen', 'Wire In Signal Layer'],
    'Parts'
);

// pcbFile.name  => 文件名
// pcbFile.size  => 文件大小（字节）
// 用 FileReader 读取为 ArrayBuffer
const reader = new FileReader();
reader.onload = () => {
    const arrayBuffer = reader.result; // ArrayBuffer
};
reader.readAsArrayBuffer(pcbFile);
```

---

## 接口总览

| 模块              | 方法                          | 用途                     |
| ----------------- | ----------------------------- | ------------------------ |
| `sys_Message`     | `showToastMessage`            | 显示 Toast 提示          |
| `sys_I18n`        | `text`                        | 获取国际化文本           |
| `sys_Dialog`      | `showInformationMessage`      | 弹出信息对话框           |
| `sys_Storage`     | `getExtensionUserConfig`      | 读取持久化配置           |
| `sys_Storage`     | `setExtensionUserConfig`      | 写入持久化配置           |
| `sys_WebSocket`   | `register`                    | 注册并连接 WebSocket     |
| `sys_WebSocket`   | `send`                        | 发送 WebSocket 消息      |
| `sys_WebSocket`   | `close`                       | 关闭 WebSocket 连接      |
| `pcb_ManufactureData` | `get3DFile`               | 获取 PCB 3D STEP 模型文件 |
