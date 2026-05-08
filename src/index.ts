import * as extensionConfig from '../extension.json';

/**
 * FreeCAD WebSocket 通信配置
 */
const FREECAD_WEBSOCKET_ID = 'freecad-pcb-exporter';
const DEFAULT_FREECAD_ADDRESS = 'ws://localhost:8766';
const STORAGE_KEY_CONNECTED = 'freecad_connected';

/**
 * 连接状态（通过 Storage 持久化，避免模块重载丢失）
 */
let isExporting = false;

function isConnectedToFreeCAD(): boolean {
	return eda.sys_Storage.getExtensionUserConfig(STORAGE_KEY_CONNECTED) === true;
}

function setConnected(value: boolean): void {
	eda.sys_Storage.setExtensionUserConfig(STORAGE_KEY_CONNECTED, value);
}

/**
 * 扩展激活时调用
 */
export function activate(status?: 'onStartupFinished', arg?: string): void {}

/**
 * 显示关于对话框
 */
export function about(): void {
	eda.sys_Dialog.showInformationMessage(
		eda.sys_I18n.text('PCB FreeCAD 导出工具 v', undefined, undefined, extensionConfig.version),
		eda.sys_I18n.text('About'),
	);
}

/**
 * 异步连接到 FreeCAD WebSocket 服务器
 * @returns Promise<void>
 */
async function connectToFreeCADAsync(): Promise<void> {
	return new Promise((resolve, reject) => {
		try {
			const timeoutId = setTimeout(() => {
				if (!isConnectedToFreeCAD()) {
					reject(new Error('连接超时，请确保FreeCAD WebSocket服务器已启动'));
				}
			}, 5000);

			eda.sys_WebSocket.register(
				FREECAD_WEBSOCKET_ID,
				DEFAULT_FREECAD_ADDRESS,
				handleFreeCADMessage,
				() => {
					clearTimeout(timeoutId);
					setConnected(true);
					eda.sys_Message.showToastMessage(
						eda.sys_I18n.text('成功连接到FreeCAD服务器!'),
						ESYS_ToastMessageType.SUCCESS
					);
					resolve();
				}
			);

		} catch (error) {
			reject(error);
		}
	});
}

/**
 * 连接到 FreeCAD WebSocket 服务器
 */
export function connectFreeCAD(): void {
	if (isConnectedToFreeCAD()) {
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('已连接到FreeCAD服务器'),
			ESYS_ToastMessageType.INFO
		);
		return;
	}

	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text('正在连接到FreeCAD服务器...'),
		ESYS_ToastMessageType.INFO
	);

	try {
		eda.sys_WebSocket.register(
			FREECAD_WEBSOCKET_ID,
			DEFAULT_FREECAD_ADDRESS,
			handleFreeCADMessage,
			onFreeCADConnected
		);
	} catch (error) {
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('连接FreeCAD失败: ${1}', undefined, undefined, (error as Error).message),
			ESYS_ToastMessageType.ERROR
		);
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('请先在FreeCAD中运行WebSocket服务器脚本'),
			ESYS_ToastMessageType.WARNING
		);
	}
}

/**
 * 连接成功回调
 */
function onFreeCADConnected(): void {
	setConnected(true);
	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text('成功连接到FreeCAD服务器!'),
		ESYS_ToastMessageType.SUCCESS
	);
}

/**
 * 处理从 FreeCAD 服务器接收到的消息
 * @param event WebSocket 消息事件
 */
function handleFreeCADMessage(event: MessageEvent<any>): void {
	try {
		const message = JSON.parse(event.data);

		switch (message.type) {
			case 'upload_progress':
				eda.sys_Message.showToastMessage(
					eda.sys_I18n.text('上传进度: ${1}% - ${2}', undefined, undefined, message.progress, message.status),
					ESYS_ToastMessageType.INFO
				);
				break;

			case 'upload_complete':
				eda.sys_Message.showToastMessage(
					eda.sys_I18n.text('文件上传完成，正在导入到FreeCAD...'),
					ESYS_ToastMessageType.SUCCESS
				);
				break;

			case 'import_complete':
				isExporting = false;
				eda.sys_Message.showToastMessage(
					eda.sys_I18n.text('PCB导入完成: ${1}', undefined, undefined, message.details || '成功导入STEP模型'),
					ESYS_ToastMessageType.SUCCESS
				);
				break;

			case 'error':
				isExporting = false;
				eda.sys_Message.showToastMessage(
					eda.sys_I18n.text('FreeCAD错误: ${1}', undefined, undefined, message.message),
					ESYS_ToastMessageType.ERROR
				);
				break;

			case 'connection_confirmed':
				setConnected(true);
				eda.sys_Message.showToastMessage(
					eda.sys_I18n.text('FreeCAD连接已确认'),
					ESYS_ToastMessageType.SUCCESS
				);
				break;

			default:
				console.log('收到FreeCAD消息:', message);
				if (message.message) {
					eda.sys_Message.showToastMessage(
						eda.sys_I18n.text('FreeCAD: ${1}', undefined, undefined, message.message),
						ESYS_ToastMessageType.INFO
					);
				}
		}
	} catch (error) {
		console.error('解析FreeCAD消息失败:', error);
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('收到无效的FreeCAD消息'),
			ESYS_ToastMessageType.WARNING
		);
	}
}

/**
 * 导出 PCB 3D STEP 文件到 FreeCAD
 */
export async function exportToFreeCAD(): Promise<void> {
	if (isExporting) {
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('正在导出中，请稍候...'),
			ESYS_ToastMessageType.INFO
		);
		return;
	}

	try {
		isExporting = true;

		if (!isConnectedToFreeCAD()) {
			eda.sys_Message.showToastMessage(
				eda.sys_I18n.text('正在连接到FreeCAD服务器...'),
				ESYS_ToastMessageType.INFO
			);

			await connectToFreeCADAsync();

			if (!isConnectedToFreeCAD()) {
				throw new Error('无法连接到FreeCAD服务器');
			}
		}

		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('正在获取PCB 3D STEP文件...'),
			ESYS_ToastMessageType.INFO
		);

		const pcbFile = await eda.pcb_ManufactureData.get3DFile(
			'pcbModel',
			'step',
			['Component Model', 'Silkscreen', 'Wire In Signal Layer'],
			'Parts'
		);

		if (!pcbFile) {
			throw new Error('无法获取PCB 3D STEP文件');
		}

		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('PCB STEP文件获取成功: ${1} (${2} KB)', undefined, undefined, pcbFile.name, (pcbFile.size / 1024).toFixed(2)),
			ESYS_ToastMessageType.SUCCESS
		);

		const fileArrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => {
				if (reader.result instanceof ArrayBuffer) {
					resolve(reader.result);
				} else {
					reject(new Error('FileReader返回的不是ArrayBuffer'));
				}
			};
			reader.onerror = () => reject(reader.error || new Error('文件读取失败'));
			reader.readAsArrayBuffer(pcbFile);
		});

		if (fileArrayBuffer.byteLength === 0) {
			throw new Error('PCB文件数据为空');
		}

		const filename = pcbFile.name.endsWith('.step') ? pcbFile.name : `${pcbFile.name}.step`;

		const message = {
			type: 'file_upload',
			filename: filename,
			size: pcbFile.size,
			data: Array.from(new Uint8Array(fileArrayBuffer))
		};

		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('正在发送文件到FreeCAD: ${1} KB', undefined, undefined, (fileArrayBuffer.byteLength / 1024).toFixed(2)),
			ESYS_ToastMessageType.INFO
		);

		eda.sys_WebSocket.send(
			FREECAD_WEBSOCKET_ID,
			JSON.stringify(message)
		);

		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('PCB STEP文件已发送到FreeCAD，等待处理...'),
			ESYS_ToastMessageType.SUCCESS
		);

	} catch (error) {
		isExporting = false;
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('导出失败: ${1}', undefined, undefined, (error as Error).message),
			ESYS_ToastMessageType.ERROR
		);
	}
}

/**
 * 断开与 FreeCAD 的连接
 */
export function disconnectFreeCAD(): void {
	if (!isConnectedToFreeCAD()) {
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('未连接到FreeCAD服务器'),
			ESYS_ToastMessageType.INFO
		);
		return;
	}

	try {
		eda.sys_WebSocket.close(
			FREECAD_WEBSOCKET_ID,
			1000,
			'用户主动断开连接'
		);

		setConnected(false);
		isExporting = false;

		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('已断开与FreeCAD的连接'),
			ESYS_ToastMessageType.INFO
		);
	} catch (error) {
		eda.sys_Message.showToastMessage(
			eda.sys_I18n.text('断开连接失败: ${1}', undefined, undefined, (error as Error).message),
			ESYS_ToastMessageType.ERROR
		);
	}
}

/**
 * 检查FreeCAD连接状态
 */
export function checkFreeCADConnection(): void {
	const connected = isConnectedToFreeCAD();
	const status = connected
		? eda.sys_I18n.text('已连接')
		: eda.sys_I18n.text('未连接');
	const messageType = connected
		? ESYS_ToastMessageType.SUCCESS
		: ESYS_ToastMessageType.WARNING;

	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text('FreeCAD连接状态: ${1}', undefined, undefined, status),
		messageType
	);
}
