import * as extensionConfig from '../extension.json';

const FREECAD_WEBSOCKET_ID = 'freecad-pcb-exporter';
const DEFAULT_FREECAD_ADDRESS = 'ws://localhost:8766';
const STORAGE_KEY_CONNECTED = 'freecad_connected';
const BIDIRECTIONAL_LISTENER_ID = 'freecad-bidirectional-sync';
const BIDIRECTIONAL_MOUSE_ID = 'freecad-bidirectional-mouse';
const MIL_TO_MM = 0.0254;
const MM_TO_MIL = 1 / 0.0254;

let isExporting = false;
let isBidirectional = false;
let designatorToPrimitiveId: Map<string, string> = new Map();
let freecadLabelToDesignator: Map<string, string> = new Map();

// 心跳检测
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let lastPongTime = 0;
const HEARTBEAT_INTERVAL_MS = 3000;
const HEARTBEAT_TIMEOUT_MS = 8000;

function startHeartbeat(): void {
	stopHeartbeat();
	lastPongTime = Date.now();
	heartbeatTimer = setInterval(() => {
		if (!isConnectedToFreeCAD()) { stopHeartbeat(); return; }
		if (Date.now() - lastPongTime > HEARTBEAT_TIMEOUT_MS) { onConnectionLost(); return; }
		try { eda.sys_WebSocket.send(FREECAD_WEBSOCKET_ID, JSON.stringify({ type: 'ping' })); }
		catch { onConnectionLost(); }
	}, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat(): void {
	if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
}

function onConnectionLost(): void {
	stopHeartbeat();
	if (!isConnectedToFreeCAD()) return;
	setConnected(false);
	if (isBidirectional) disableBidirectional();
	eda.sys_Message.showToastMessage(eda.sys_I18n.text('已断开与FreeCAD的连接'), ESYS_ToastMessageType.WARNING);
}

function isConnectedToFreeCAD(): boolean {
	return eda.sys_Storage.getExtensionUserConfig(STORAGE_KEY_CONNECTED) === true;
}

function setConnected(value: boolean): void {
	eda.sys_Storage.setExtensionUserConfig(STORAGE_KEY_CONNECTED, value);
}

export function activate(status?: 'onStartupFinished', arg?: string): void {}

export function about(): void {
	eda.sys_Dialog.showInformationMessage(
		eda.sys_I18n.text('PCB FreeCAD 导出工具 v', undefined, undefined, extensionConfig.version),
		eda.sys_I18n.text('About'),
	);
}

// ==================== 连接 ====================

async function connectToFreeCADAsync(): Promise<void> {
	return new Promise((resolve, reject) => {
		try {
			const timeoutId = setTimeout(() => {
				if (!isConnectedToFreeCAD()) reject(new Error('连接超时'));
			}, 5000);
			eda.sys_WebSocket.register(FREECAD_WEBSOCKET_ID, DEFAULT_FREECAD_ADDRESS, handleFreeCADMessage, () => {
				clearTimeout(timeoutId);
				setConnected(true);
				lastPongTime = Date.now();
				startHeartbeat();
				resolve();
			});
		} catch (error) { reject(error); }
	});
}

export function connectFreeCAD(): void {
	if (isConnectedToFreeCAD()) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('已连接到FreeCAD服务器'), ESYS_ToastMessageType.INFO);
		return;
	}
	eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在连接到FreeCAD服务器...'), ESYS_ToastMessageType.INFO);
	try {
		eda.sys_WebSocket.register(FREECAD_WEBSOCKET_ID, DEFAULT_FREECAD_ADDRESS, handleFreeCADMessage, () => {
			setConnected(true);
			lastPongTime = Date.now();
			startHeartbeat();
			eda.sys_Message.showToastMessage(eda.sys_I18n.text('成功连接到FreeCAD服务器!'), ESYS_ToastMessageType.SUCCESS);
		});
	} catch (error) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('连接FreeCAD失败: ${1}', undefined, undefined, (error as Error).message), ESYS_ToastMessageType.ERROR);
	}
}

// ==================== 消息处理 ====================

function handleFreeCADMessage(event: MessageEvent<any>): void {
	try {
		const message = JSON.parse(event.data);
		switch (message.type) {
			case 'pong':
				lastPongTime = Date.now();
				break;
			case 'connection_confirmed':
				setConnected(true);
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('FreeCAD连接已确认'), ESYS_ToastMessageType.SUCCESS);
				break;
			case 'upload_progress':
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('处理中 ${1}%', undefined, undefined, message.progress), ESYS_ToastMessageType.INFO);
				break;
			case 'upload_complete':
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('文件上传完成，正在导入到FreeCAD...'), ESYS_ToastMessageType.SUCCESS);
				break;
			case 'import_complete':
				isExporting = false;
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('PCB导入完成: ${1}', undefined, undefined, message.details || '成功'), ESYS_ToastMessageType.SUCCESS);
				break;
			case 'error':
				isExporting = false;
				eda.sys_Message.showToastMessage(eda.sys_I18n.text('FreeCAD错误: ${1}', undefined, undefined, message.message), ESYS_ToastMessageType.ERROR);
				break;
			case 'mapping_result':
				handleMappingResult(message.mapping);
				break;
			case 'position_update_from_freecad':
				handlePositionUpdateFromFreecad(message);
				break;
			case 'cross_probe_from_freecad':
				handleCrossProbeFromFreecad(message);
				break;
			default:
				if (message.message) {
					eda.sys_Message.showToastMessage(eda.sys_I18n.text('FreeCAD: ${1}', undefined, undefined, message.message), ESYS_ToastMessageType.INFO);
				}
		}
	} catch {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('收到无效的FreeCAD消息'), ESYS_ToastMessageType.WARNING);
	}
}

// ==================== 导出 ====================

export async function exportToFreeCAD(): Promise<void> {
	if (isExporting) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在导出中，请稍候...'), ESYS_ToastMessageType.INFO);
		return;
	}
	try {
		isExporting = true;
		if (!isConnectedToFreeCAD()) {
			eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在连接到FreeCAD服务器...'), ESYS_ToastMessageType.INFO);
			await connectToFreeCADAsync();
			if (!isConnectedToFreeCAD()) throw new Error('无法连接到FreeCAD服务器');
		}
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在获取PCB 3D STEP文件...'), ESYS_ToastMessageType.INFO);
		const pcbFile = await eda.pcb_ManufactureData.get3DFile('pcbModel', 'step', ['Component Model', 'Silkscreen', 'Wire In Signal Layer'], 'Parts');
		if (!pcbFile) throw new Error('无法获取PCB 3D STEP文件');
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('PCB STEP文件获取成功: ${1} (${2} KB)', undefined, undefined, pcbFile.name, (pcbFile.size / 1024).toFixed(2)), ESYS_ToastMessageType.SUCCESS);

		const fileArrayBuffer = await new Promise<ArrayBuffer>((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => { if (reader.result instanceof ArrayBuffer) resolve(reader.result); else reject(new Error('FileReader返回的不是ArrayBuffer')); };
			reader.onerror = () => reject(reader.error || new Error('文件读取失败'));
			reader.readAsArrayBuffer(pcbFile);
		});
		if (fileArrayBuffer.byteLength === 0) throw new Error('PCB文件数据为空');

		const filename = pcbFile.name.endsWith('.step') ? pcbFile.name : `${pcbFile.name}.step`;
		eda.sys_WebSocket.send(FREECAD_WEBSOCKET_ID, JSON.stringify({ type: 'file_upload', filename, size: pcbFile.size, data: Array.from(new Uint8Array(fileArrayBuffer)) }));
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在发送文件到FreeCAD: ${1} KB', undefined, undefined, (fileArrayBuffer.byteLength / 1024).toFixed(2)), ESYS_ToastMessageType.INFO);
	} catch (error) {
		isExporting = false;
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('导出失败: ${1}', undefined, undefined, (error as Error).message), ESYS_ToastMessageType.ERROR);
	}
}

// ==================== 双向交互 ====================

export async function enableBidirectional(): Promise<void> {
	if (isBidirectional) return;

	if (!isConnectedToFreeCAD()) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('正在连接到FreeCAD服务器...'), ESYS_ToastMessageType.INFO);
		try { await connectToFreeCADAsync(); }
		catch (error) {
			eda.sys_Message.showToastMessage(eda.sys_I18n.text('连接FreeCAD失败: ${1}', undefined, undefined, (error as Error).message), ESYS_ToastMessageType.ERROR);
			return;
		}
	}

	isBidirectional = true;

	// 1. 立即构建 EDA 端映射（designator → primitiveId）
	try {
		const components = await eda.pcb_PrimitiveComponent.getAll();
		for (const comp of components) {
			const designator = comp.getState_Designator();
			const primitiveId = comp.getState_PrimitiveId();
			if (designator) {
				designatorToPrimitiveId.set(designator, primitiveId);
			primitiveIdToDesignator.set(primitiveId, designator);
			}
		}
		console.log(`[双向交互] 已获取 ${designatorToPrimitiveId.size} 个元件映射`);
	} catch (error) {
		console.error('[双向交互] 获取元件列表失败:', error);
	}

	// 2. 注册事件监听
	eda.pcb_Event.addPrimitiveEventListener(BIDIRECTIONAL_LISTENER_ID, 'all', onPcbPrimitiveChange);
	eda.pcb_Event.addMouseEventListener(BIDIRECTIONAL_MOUSE_ID, 'selected', onPcbMouseSelect);
	console.log('[双向交互] 事件监听已注册, isBidirectional=' + isBidirectional);

	// 3. 全量导出 STEP
	await exportToFreeCAD();

	// 4. 发送映射请求给 FreeCAD（FreeCAD import 完成后处理）
	if (designatorToPrimitiveId.size > 0) {
		const componentData: Array<{ designator: string; x: number; y: number; rotation: number }> = [];
		for (const [designator, primitiveId] of designatorToPrimitiveId) {
			try {
				const comp = await eda.pcb_PrimitiveComponent.get(primitiveId);
				if (comp) componentData.push({ designator, x: comp.getState_X() * MIL_TO_MM, y: comp.getState_Y() * MIL_TO_MM, rotation: comp.getState_Rotation() });
			} catch {}
		}
		sendToFreeCAD({ type: 'build_mapping', components: componentData });
		console.log(`[双向交互] 已发送 ${componentData.length} 个元件映射到FreeCAD`);
	}

	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text('双向交互已启动，点击元件可以双向定位，拖动元件可以同步移动'),
		ESYS_ToastMessageType.SUCCESS
	);
}

export function disableBidirectional(): void {
	if (!isBidirectional) return;
	isBidirectional = false;
	try { eda.pcb_Event.removeEventListener(BIDIRECTIONAL_LISTENER_ID); } catch {}
	try { eda.pcb_Event.removeEventListener(BIDIRECTIONAL_MOUSE_ID); } catch {}
	sendToFreeCAD({ type: 'disable_monitor' });
	designatorToPrimitiveId.clear();
	primitiveIdToDesignator.clear();
	freecadLabelToDesignator.clear();
	eda.sys_Message.showToastMessage(eda.sys_I18n.text('双向交互已停止'), ESYS_ToastMessageType.INFO);
}

function handleMappingResult(mapping: Array<{ designator: string; freecadLabel: string }>): void {
	freecadLabelToDesignator.clear();
	for (const item of mapping) {
		freecadLabelToDesignator.set(item.freecadLabel, item.designator);
	}
	console.log(`[双向交互] FreeCAD返回 ${mapping.length} 个对象映射`);
	if (mapping.length > 0) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('元件映射建立成功: ${1} 个元件', undefined, undefined, mapping.length), ESYS_ToastMessageType.SUCCESS);
		sendToFreeCAD({ type: 'enable_monitor' });
	} else {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('元件映射失败'), ESYS_ToastMessageType.WARNING);
	}
}

// 反向查找：primitiveId → designator
let primitiveIdToDesignator: Map<string, string> = new Map();

function onPcbPrimitiveChange(eventType: string, props: any[]): void {
	if (!isBidirectional) return;
	for (const prop of props) {
		// 依次尝试：直接 designator → 父元件 designator → 通过 pid 反查 → 通过 parentPid 反查
		const designator =
			prop.designator ||
			prop.parentComponentDesignator ||
			primitiveIdToDesignator.get(prop.primitiveId) ||
			primitiveIdToDesignator.get(prop.parentComponentPrimitiveId);
		console.log(`[双向交互] 图元 type=${eventType} pid=${prop.primitiveId} parentPid=${prop.parentComponentPrimitiveId} desig=${prop.designator} parentDesig=${prop.parentComponentDesignator} resolved=${designator}`);
		if (!designator) continue;
		if (eventType === 'move' || eventType === 'modify') {
			syncPositionToFreecad(prop.primitiveId, designator);
		} else if (eventType === 'delete') {
			sendToFreeCAD({ type: 'delete_object', designator });
		}
	}
}

async function syncPositionToFreecad(primitiveId: string, designator: string): Promise<void> {
	try {
		const targetId = designatorToPrimitiveId.get(designator) || primitiveId;
		const comp = await eda.pcb_PrimitiveComponent.get(targetId);
		if (!comp) {
			console.log(`[双向交互] 未找到元件: designator=${designator} targetId=${targetId}`);
			return;
		}
		// EDA 坐标是 mil，FreeCAD 用 mm
		const x_mm = comp.getState_X() * MIL_TO_MM;
		const y_mm = comp.getState_Y() * MIL_TO_MM;
		const rot = comp.getState_Rotation();
		console.log(`[双向交互] 同步位置: ${designator} x=${x_mm.toFixed(2)}mm y=${y_mm.toFixed(2)}mm rot=${rot}`);
		sendToFreeCAD({ type: 'position_update', designator, x: x_mm, y: y_mm, rotation: rot });
	} catch (error) { console.error('[双向交互] 同步位置失败:', error); }
}

async function onPcbMouseSelect(eventType: string, props: any[]): Promise<void> {
	if (!isBidirectional) return;
	if (!props || props.length === 0) return;
	try {
		const designator = props[0].parentComponentDesignator || props[0].designator;
		if (designator) sendToFreeCAD({ type: 'cross_probe', designator });
	} catch (error) { console.error('[双向交互] 交叉定位失败:', error); }
}

async function handlePositionUpdateFromFreecad(message: any): Promise<void> {
	if (!isBidirectional) return;
	const designator = message.designator;
	if (!designator) return;
	const primitiveId = designatorToPrimitiveId.get(designator);
	if (!primitiveId) return;
	try {
		// FreeCAD 坐标是 mm，EDA 用 mil
		const comp = await eda.pcb_PrimitiveComponent.get(primitiveId);
		if (!comp) return;
		comp.setState_X(message.x * MM_TO_MIL);
		comp.setState_Y(message.y * MM_TO_MIL);
		comp.setState_Rotation(message.rotation);
		await comp.done();
	} catch (error) { console.error('[双向交互] FreeCAD→EDA位置更新失败:', error); }
}

async function handleCrossProbeFromFreecad(message: any): Promise<void> {
	if (!isBidirectional) return;
	const designator = message.designator;
	if (!designator) return;
	try {
		await eda.pcb_SelectControl.doCrossProbeSelect([designator], undefined, undefined, true, true);
		if (message.x !== undefined && message.y !== undefined) {
			// navigateToCoordinates 用 mil
			await eda.pcb_Document.navigateToCoordinates(message.x * MM_TO_MIL, message.y * MM_TO_MIL);
		}
	} catch (error) { console.error('[双向交互] FreeCAD→EDA交叉定位失败:', error); }
}

function sendToFreeCAD(data: Record<string, any>): void {
	try { eda.sys_WebSocket.send(FREECAD_WEBSOCKET_ID, JSON.stringify(data)); }
	catch (error) { console.error('[双向交互] 发送失败:', error); setConnected(false); }
}

// ==================== 断开连接 ====================

export function disconnectFreeCAD(): void {
	if (isBidirectional) disableBidirectional();
	stopHeartbeat();
	if (!isConnectedToFreeCAD()) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('未连接到FreeCAD服务器'), ESYS_ToastMessageType.INFO);
		return;
	}
	try {
		eda.sys_WebSocket.close(FREECAD_WEBSOCKET_ID, 1000, '用户主动断开连接');
		setConnected(false);
		isExporting = false;
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('已断开与FreeCAD的连接'), ESYS_ToastMessageType.INFO);
	} catch (error) {
		eda.sys_Message.showToastMessage(eda.sys_I18n.text('断开连接失败: ${1}', undefined, undefined, (error as Error).message), ESYS_ToastMessageType.ERROR);
	}
}

export function checkFreeCADConnection(): void {
	const connected = isConnectedToFreeCAD();
	eda.sys_Message.showToastMessage(
		eda.sys_I18n.text('FreeCAD连接状态: ${1}', undefined, undefined, connected ? eda.sys_I18n.text('已连接') : eda.sys_I18n.text('未连接')),
		connected ? ESYS_ToastMessageType.SUCCESS : ESYS_ToastMessageType.WARNING
	);
}
