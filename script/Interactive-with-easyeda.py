#!/usr/bin/env python3
"""
PCB FreeCAD导入器 - WebSocket服务器（支持双向交互）

使用方法:
1. 在FreeCAD中打开宏编辑器
2. 复制此脚本内容到宏编辑器
3. 运行宏启动WebSocket服务器
4. 在嘉立创EDA中点击"连接FreeCAD"
5. 点击"导出3D到FreeCAD"发送PCB STEP文件
6. 点击"启用双向交互"开启位置同步和交叉定位

FreeCAD相关：
点击：视图 → 面板 → 报告视图 可以查看脚本运行日志

服务器地址: ws://localhost:8766
"""

import sys
import os
import subprocess

def get_python_executable():
    """获取正确的Python解释器路径（FreeCAD中sys.executable指向FreeCAD.exe）"""
    if 'python' in os.path.basename(sys.executable).lower():
        return sys.executable

    freecad_dir = os.path.dirname(sys.executable)
    for name in ('python3.exe', 'python.exe', 'python'):
        candidate = os.path.join(freecad_dir, name)
        if os.path.isfile(candidate):
            return candidate

    bin_dir = os.path.join(freecad_dir, 'bin')
    for name in ('python3.exe', 'python.exe', 'python'):
        candidate = os.path.join(bin_dir, name)
        if os.path.isfile(candidate):
            return candidate

    return sys.executable


def check_and_install_websockets():
    """检查并自动安装websockets库"""
    print("检查websockets库...")

    try:
        import websockets
        print("websockets库已安装")
        return True
    except ImportError:
        print("websockets库未安装，正在自动安装...")

        try:
            python_exe = get_python_executable()
            print(f"使用Python解释器: {python_exe}")
            result = subprocess.run([
                python_exe, "-m", "pip", "install", "websockets==13.1"
            ], capture_output=True, text=True, check=True)

            print("websockets库安装成功")
            print(f"安装输出: {result.stdout}")

            import websockets
            return True

        except subprocess.CalledProcessError as e:
            print(f"websockets库自动安装失败: {e}")
            print(f"错误输出: {e.stderr}")
            print("请手动安装:")
            print(f'  "{python_exe}" -m pip install websockets==13.1')
            return False
        except Exception as e:
            print(f"安装过程中出现错误: {e}")
            return False

if not check_and_install_websockets():
    print("无法安装websockets库，脚本退出")
    sys.exit(1)

import websockets
import asyncio
import json
import re
import threading
import tempfile
import shutil
import queue
import time


class MessageQueue:
    """线程安全的消息队列"""

    def __init__(self):
        self.queue = queue.Queue()

    def put(self, message):
        self.queue.put(message)

    def get_all(self):
        messages = []
        while not self.queue.empty():
            try:
                messages.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return messages


class WebSocketPCBServer:
    def __init__(self, host="0.0.0.0", port=8766):
        self.host = host
        self.port = port
        self.server = None
        self.loop = None
        self.is_running = False
        self.clients = set()
        self.message_queue = MessageQueue()
        self.server_thread = None

        # 双向交互状态
        self.designator_map = {}       # designator → FreeCAD object label
        self.label_map = {}            # FreeCAD object label → designator
        self.last_positions = {}       # label → {x, y, z, yaw, pitch, roll}
        self.designator_groups = {}   # designator → [label1, label2, ...] 同组对象一起移动
        self.center_offset = {'x': 0, 'y': 0, 'z': 0}  # 居中偏移量
        self.monitor_active = False
        self.monitor_timer = None
        self.last_update_source = None  # 防止循环更新: 'eda' 或 None
        self.last_selected_labels = set()  # 上次选中的对象 label 集合
        self.last_freecad_move_time = 0   # 用户在 FreeCAD 中最后操作的时间戳

        print(f"初始化WebSocket服务器 {host}:{port}")

    def _resolve_designator(self, designator):
        """大小写无关查找 designator 实际存储的 key"""
        if designator in self.designator_map:
            return designator
        for key in self.designator_map:
            if key.upper() == designator.upper():
                return key
        return None

    @staticmethod
    def _position_equal(a, b, pos_tol=0.01, rot_tol=0.1):
        """比较两个位置是否相同（带容差），避免浮点漂移触发误检测"""
        return (abs(a['x'] - b['x']) < pos_tol and
                abs(a['y'] - b['y']) < pos_tol and
                abs(a['z'] - b['z']) < pos_tol and
                abs(a['yaw'] - b['yaw']) < rot_tol)

    async def register_client(self, websocket, path=None):
        self.clients.add(websocket)
        try:
            client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        except Exception:
            client_addr = "unknown"

        print(f"客户端连接: {client_addr}")

        await websocket.send(json.dumps({
            "type": "connection_confirmed",
            "message": "成功连接到FreeCAD PCB导入器"
        }))

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"客户端断开: {client_addr}")
        finally:
            self.clients.discard(websocket)

    async def handle_message(self, websocket, message):
        try:
            data = json.loads(message)
            message_type = data.get('type')
            if message_type == 'file_upload':
                await self.handle_file_upload(websocket, data)
            elif message_type == 'ping':
                await websocket.send(json.dumps({"type": "pong"}))
            elif message_type == 'build_mapping':
                self.handle_build_mapping(data)
            elif message_type == 'position_update':
                self.handle_position_update(data)
            elif message_type == 'delete_object':
                self.handle_delete_object(data)
            elif message_type == 'cross_probe':
                self.handle_cross_probe(data)
            elif message_type == 'rename_designator':
                self.handle_rename_designator(data)
            elif message_type == 'enable_monitor':
                self.message_queue.put({'type': 'enable_monitor'})
            elif message_type == 'disable_monitor':
                self.message_queue.put({'type': 'disable_monitor'})
            else:
                print(f"未知消息类型: {message_type}")

        except json.JSONDecodeError:
            await self.send_error(websocket, "无效的JSON消息")
        except Exception as e:
            await self.send_error(websocket, f"消息处理错误: {str(e)}")

    # ==================== 文件导入 ====================

    async def handle_file_upload(self, websocket, data):
        try:
            filename = data.get('filename')
            file_size = data.get('size')
            file_data = data.get('data')

            if not all([filename, file_size, file_data]):
                await self.send_error(websocket, "文件数据不完整")
                return

            print(f"接收文件: {filename} ({file_size} bytes)")

            await websocket.send(json.dumps({
                "type": "upload_progress",
                "progress": 50,
                "status": "processing"
            }))

            file_bytes = bytes(file_data)
            temp_dir = tempfile.mkdtemp(prefix="pcb_step_")
            temp_file_path = os.path.join(temp_dir, filename)

            with open(temp_file_path, 'wb') as f:
                f.write(file_bytes)

            await websocket.send(json.dumps({
                "type": "upload_progress",
                "progress": 100,
                "status": "upload_done"
            }))

            await websocket.send(json.dumps({
                "type": "upload_complete",
                "message": "开始导入..."
            }))

            import_task = {
                'type': 'import_step',
                'file_path': temp_file_path,
                'temp_dir': temp_dir,
                'filename': filename,
                'sync': data.get('sync', False),
            }
            self.message_queue.put(import_task)

        except Exception as e:
            await self.send_error(websocket, f"文件处理错误: {str(e)}")

    def import_step_file(self, file_path, sync=False):
        """在主线程中调用，导入STEP文件到FreeCAD"""
        try:
            import FreeCAD
            import ImportGui

            print(f"导入STEP文件: {file_path}")

            if sync and self.designator_map:
                # 同步模式：清除旧对象，在同一文档中插入新模型
                doc = FreeCAD.getActiveDocument()
                if doc:
                    obj_names = []
                    for obj in list(doc.Objects):
                        try:
                            obj_names.append(obj.Name)
                        except Exception:
                            pass
                    for name in obj_names:
                        try:
                            if doc.getObject(name) is not None:
                                doc.removeObject(name)
                        except Exception:
                            pass
                    ImportGui.insert(file_path, doc.Name)
                    try:
                        doc.recompute()
                    except Exception as e:
                        print(f"recompute 失败: {e}")
                    print(f"同步更新完成，共 {len(doc.Objects)} 个对象")
                    return True

            # 首次导入：创建新文档
            ImportGui.open(file_path)

            doc = FreeCAD.ActiveDocument
            if doc is None:
                print("错误: 导入后没有活动文档")
                return False

            num_objects = len(doc.Objects)
            print(f"导入成功，共 {num_objects} 个对象")

            self.center_model(doc)

            try:
                doc.recompute()
            except Exception as e:
                print(f"recompute 失败: {e}")

            try:
                import FreeCADGui
                FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
                FreeCADGui.SendMsgToActiveView("ViewFit")
            except Exception as e:
                print(f"视图调整失败（不影响导入）: {e}")

            return True
        except Exception as e:
            print(f"导入失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def center_model(self, doc):
        """将文档中所有对象居中到原点"""
        try:
            import FreeCAD

            bb_min_x = float('inf')
            bb_min_y = float('inf')
            bb_min_z = float('inf')
            bb_max_x = float('-inf')
            bb_max_y = float('-inf')
            bb_max_z = float('-inf')
            has_valid = False

            for obj in doc.Objects:
                try:
                    if hasattr(obj, 'Shape') and obj.Shape is not None and hasattr(obj.Shape, 'BoundBox'):
                        bb = obj.Shape.BoundBox
                    elif hasattr(obj, 'Mesh') and obj.Mesh is not None and hasattr(obj.Mesh, 'BoundBox'):
                        bb = obj.Mesh.BoundBox
                    else:
                        continue

                    bb_min_x = min(bb_min_x, bb.XMin)
                    bb_min_y = min(bb_min_y, bb.YMin)
                    bb_min_z = min(bb_min_z, bb.ZMin)
                    bb_max_x = max(bb_max_x, bb.XMax)
                    bb_max_y = max(bb_max_y, bb.YMax)
                    bb_max_z = max(bb_max_z, bb.ZMax)
                    has_valid = True
                except Exception:
                    continue

            if not has_valid:
                return

            cx = (bb_min_x + bb_max_x) / 2
            cy = (bb_min_y + bb_max_y) / 2
            cz = (bb_min_z + bb_max_z) / 2

            if abs(cx) < 0.01 and abs(cy) < 0.01 and abs(cz) < 0.01:
                self.center_offset = {'x': 0, 'y': 0, 'z': 0}
                return

            self.center_offset = {'x': cx, 'y': cy, 'z': cz}
            print(f"居中偏移量: cx={cx:.2f} cy={cy:.2f} cz={cz:.2f}")

            for obj in doc.Objects:
                if hasattr(obj, 'Placement'):
                    try:
                        p = obj.Placement
                        new_base = FreeCAD.Vector(p.Base.x - cx, p.Base.y - cy, p.Base.z - cz)
                        obj.Placement = FreeCAD.Placement(new_base, p.Rotation)
                    except Exception:
                        continue

            print("模型已居中到原点")
        except Exception as e:
            print(f"居中处理失败（不影响导入）: {e}")

    # ==================== 双向交互 ====================

    def handle_build_mapping(self, data):
        """建立 designator → FreeCAD 对象映射"""
        components = data.get('components', [])
        if not components:
            return

        self.message_queue.put({
            'type': 'build_mapping',
            'components': components
        })

    def do_build_mapping(self, components):
        """在主线程中执行映射建立"""
        try:
            import FreeCAD

            doc = FreeCAD.ActiveDocument
            if not doc:
                print("[映射] 没有活动文档")
                self.send_to_clients({"type": "mapping_result", "mapping": []})
                return

            # 收集 FreeCAD 所有对象（含 label 和位置）
            freecad_objects = []
            for obj in doc.Objects:
                try:
                    info = {'label': obj.Label, 'name': obj.Name, 'x': 0, 'y': 0, 'z': 0}
                    if hasattr(obj, 'Shape') and obj.Shape is not None and hasattr(obj.Shape, 'BoundBox'):
                        bb = obj.Shape.BoundBox
                        info['x'] = (bb.XMin + bb.XMax) / 2
                        info['y'] = (bb.YMin + bb.YMax) / 2
                        info['z'] = (bb.ZMin + bb.ZMax) / 2
                    elif hasattr(obj, 'Placement'):
                        p = obj.Placement.Base
                        info['x'] = p.x
                        info['y'] = p.y
                        info['z'] = p.z
                    freecad_objects.append(info)
                except Exception:
                    pass

            # 打印调试信息
            print(f"[映射] EDA 发送 {len(components)} 个元件:")
            for c in components:
                print(f"  EDA: {c['designator']} x={c.get('x','?')} y={c.get('y','?')} rot={c.get('rotation','?')}")
            print(f"[映射] FreeCAD 有 {len(freecad_objects)} 个对象:")
            for o in freecad_objects:
                print(f"  FC: Label='{o['label']}' Name='{o['name']}' x={o['x']:.2f} y={o['y']:.2f} z={o['z']:.2f}")

            self.designator_map.clear()
            self.label_map.clear()
            mapping = []
            used_fc_objects = set()

            # 第一轮：label 精确匹配（忽略大小写）
            for comp in components:
                designator = comp['designator']
                for i, fc_obj in enumerate(freecad_objects):
                    if i in used_fc_objects:
                        continue
                    if fc_obj['label'].upper() == designator.upper():
                        self.designator_map[designator] = fc_obj['label']
                        self.label_map[fc_obj['label']] = designator
                        mapping.append({'designator': designator, 'freecadLabel': fc_obj['label']})
                        used_fc_objects.add(i)
                        break

            # 第二轮：label 单词边界匹配（R5 匹配 "R5~R0402XX" 但不匹配 "R50"）
            for comp in components:
                designator = comp['designator']
                if designator in self.designator_map:
                    continue
                # 前面不能是字母或数字，后面不能是数字（防止 R1 匹配 R10）
                pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(designator) + r'(?![0-9])', re.IGNORECASE)
                for i, fc_obj in enumerate(freecad_objects):
                    if i in used_fc_objects:
                        continue
                    if pattern.search(fc_obj['label']):
                        self.designator_map[designator] = fc_obj['label']
                        self.label_map[fc_obj['label']] = designator
                        mapping.append({'designator': designator, 'freecadLabel': fc_obj['label']})
                        used_fc_objects.add(i)
                        break

            # 第三轮：位置匹配（EDA 已发送 mm 坐标，需补偿居中偏移）
            # 尝试多种坐标轴映射：EDA(X,Y) 可能对应 FreeCAD (X,Y), (X,Z), (X,-Y) 等
            TOLERANCE_MM = 2.0  # 2mm 容忍度
            cx = self.center_offset['x']
            cy = self.center_offset['y']
            cz = self.center_offset['z']
            for comp in components:
                designator = comp['designator']
                if designator in self.designator_map:
                    continue
                eda_x_mm = comp.get('x', 0)
                eda_y_mm = comp.get('y', 0)
                best_match = None
                best_dist = float('inf')
                for i, fc_obj in enumerate(freecad_objects):
                    if i in used_fc_objects:
                        continue
                    # FC 对象位置 = 原始位置 - 居中偏移，加回偏移得到原始坐标
                    rx = fc_obj['x'] + cx
                    ry = fc_obj['y'] + cy
                    rz = fc_obj['z'] + cz
                    # 尝试多种轴映射，取最小距离
                    dists = [
                        ((rx - eda_x_mm) ** 2 + (ry - eda_y_mm) ** 2) ** 0.5,   # XY
                        ((rx - eda_x_mm) ** 2 + (rz - eda_y_mm) ** 2) ** 0.5,   # XZ (板子在XZ平面)
                        ((rx - eda_x_mm) ** 2 + (-ry - eda_y_mm) ** 2) ** 0.5,  # X,-Y
                        ((rx - eda_x_mm) ** 2 + (-rz - eda_y_mm) ** 2) ** 0.5,  # X,-Z
                    ]
                    dist = min(dists)
                    if dist < TOLERANCE_MM and dist < best_dist:
                        best_dist = dist
                        best_match = i
                if best_match is not None:
                    fc_obj = freecad_objects[best_match]
                    self.designator_map[designator] = fc_obj['label']
                    self.label_map[fc_obj['label']] = designator
                    mapping.append({'designator': designator, 'freecadLabel': fc_obj['label']})
                    used_fc_objects.add(best_match)
                    print(f"  [位置匹配] {designator} -> '{fc_obj['label']}' (dist={best_dist:.2f}mm)")

            print(f"[映射] 完成: {len(mapping)}/{len(components)} 个元件匹配")

            # 构建同组对象：同一位置的对象归为一组，移动时一起移
            # 收集所有主对象的 label，避免将其他元件的主对象归入错误分组
            main_labels = set(self.designator_map.values())
            self.designator_groups.clear()
            TOLERANCE = 0.5  # mm，缩小容忍度避免误匹配
            for designator, main_label in self.designator_map.items():
                # 找到主对象的中心位置
                main_pos = None
                for o in freecad_objects:
                    if o['label'] == main_label:
                        main_pos = (o['x'], o['y'])
                        break
                if not main_pos:
                    continue
                # 只将非主对象的、同位置的对象归入分组
                group = [main_label]  # 主对象始终在组内
                for o in freecad_objects:
                    if o['label'] == main_label:
                        continue
                    # 跳过其他元件的主对象
                    if o['label'] in main_labels:
                        continue
                    dist = ((o['x'] - main_pos[0]) ** 2 + (o['y'] - main_pos[1]) ** 2) ** 0.5
                    if dist < TOLERANCE:
                        group.append(o['label'])
                        if o['label'] not in self.label_map:
                            self.label_map[o['label']] = designator
                self.designator_groups[designator] = group
                if len(group) > 1:
                    print(f"  [分组] {designator}: {len(group)} 个对象 -> {group}")

            # 记录初始位置
            self.snapshot_positions()

            self.send_to_clients({"type": "mapping_result", "mapping": mapping})

        except Exception as e:
            print(f"建立映射失败: {e}")
            import traceback
            traceback.print_exc()
            self.send_to_clients({"type": "mapping_result", "mapping": []})

    def handle_position_update(self, data):
        """EDA → FreeCAD 位置更新"""
        designator = data.get('designator')
        if not designator:
            return
        print(f"[位置更新] 收到 EDA 位置更新: {designator} x={data.get('x')} y={data.get('y')} rot={data.get('rotation')}")
        self.message_queue.put({
            'type': 'position_update',
            'designator': designator,
            'x': data.get('x', 0),
            'y': data.get('y', 0),
            'rotation': data.get('rotation', 0)
        })

    def do_position_update(self, designator, x, y, rotation):
        """在主线程中更新对象位置（x/y 是 EDA 原始 mm 坐标，需减去居中偏移）"""
        try:
            import FreeCAD
            import FreeCAD as FC

            # 如果用户最近在 FreeCAD 中操作过（1秒内），丢弃 EDA 的反馈更新
            if time.time() - self.last_freecad_move_time < 1.0:
                return

            resolved = self._resolve_designator(designator)
            if not resolved:
                return
            designator = resolved

            group = self.designator_groups.get(designator, [])
            if not group:
                return

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            # 标记来源为 EDA，防止循环
            self.last_update_source = 'eda'

            fc_x = x - self.center_offset['x']
            fc_y = y - self.center_offset['y']

            main_label = self.designator_map.get(designator)
            main_obj = None
            for o in doc.Objects:
                if o.Label == main_label and hasattr(o, 'Placement'):
                    main_obj = o
                    break

            if not main_obj:
                return

            old_p = main_obj.Placement
            dx = fc_x - old_p.Base.x
            dy = fc_y - old_p.Base.y
            old_yaw = old_p.Rotation.getYawPitchRoll()[0]
            d_rot = rotation - old_yaw

            new_rot = FC.Rotation(FC.Vector(0, 0, 1), rotation)

            print(f"[位置更新] {designator}: EDA({x:.2f},{y:.2f}) FC({fc_x:.2f},{fc_y:.2f}) dx={dx:.2f} dy={dy:.2f}, {len(group)} 个对象")

            # 移动同组所有对象
            for label in group:
                for o in doc.Objects:
                    if o.Label == label and hasattr(o, 'Placement'):
                        p = o.Placement
                        if label == main_label:
                            o.Placement = FC.Placement(FC.Vector(fc_x, fc_y, p.Base.z), new_rot)
                        else:
                            o.Placement = FC.Placement(
                                FC.Vector(p.Base.x + dx, p.Base.y + dy, p.Base.z),
                                FC.Rotation(FC.Vector(0, 0, 1), p.Rotation.getYawPitchRoll()[0] + d_rot)
                            )
                        break

            # 更新快照
            self.snapshot_positions()

        except Exception as e:
            print(f"更新位置失败: {e}")
        finally:
            self.last_update_source = None

    def handle_rename_designator(self, data):
        """EDA 通知位号变更"""
        old = data.get('old')
        new = data.get('new')
        if not old or not new:
            return
        self.message_queue.put({
            'type': 'rename_designator',
            'old': old,
            'new': new
        })

    def do_rename_designator(self, old, new):
        """在���线程中更新位号映射，并修改 FreeCAD 对象的 Label"""
        try:
            import FreeCAD
            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            resolved_old = self._resolve_designator(old)
            if not resolved_old:
                print(f"[重命名] 未找到旧位号={old} 的映射")
                return
            old = resolved_old

            old_label = self.designator_map.pop(old, None)
            if not old_label:
                return

            # 计算新 Label：将旧 Label 中的旧位号替换为新位号
            new_label = old_label.replace(old, new) if old in old_label else new

            # 更新所有映射表
            self.designator_map[new] = new_label

            group = self.designator_groups.pop(old, None)
            if group:
                self.designator_groups[new] = group
                # 重命名同组所有对象的 Label
                old_group = self.designator_groups.get(new, [])
                new_group = []
                for lbl in old_group:
                    obj_lbl = lbl.replace(old, new) if old in lbl else lbl
                    new_group.append(obj_lbl)
                    # 更新 label_map
                    desig = self.label_map.pop(lbl, None)
                    if desig:
                        self.label_map[obj_lbl] = new if desig == old else desig
                    # 更新 last_positions
                    pos = self.last_positions.pop(lbl, None)
                    if pos:
                        self.last_positions[obj_lbl] = pos
                    # 更新 FreeCAD 对象 Label
                    for o in doc.Objects:
                        if o.Label == lbl:
                            o.Label = obj_lbl
                            break
                self.designator_groups[new] = new_group
            else:
                # 没有分组，单独处理
                desig = self.label_map.pop(old_label, None)
                if desig:
                    self.label_map[new_label] = new
                pos = self.last_positions.pop(old_label, None)
                if pos:
                    self.last_positions[new_label] = pos
                for o in doc.Objects:
                    if o.Label == old_label:
                        o.Label = new_label
                        break

            print(f"[重命名] {old}({old_label}) → {new}({new_label})")
        except Exception as e:
            print(f"重命名失败: {e}")

    def handle_delete_object(self, data):
        """EDA → FreeCAD 删除对象"""
        designator = data.get('designator')
        if not designator:
            return
        self.message_queue.put({
            'type': 'delete_object',
            'designator': designator
        })

    def do_delete_object(self, designator):
        """在主线程中删除对象及其同组对象"""
        try:
            import FreeCAD

            resolved = self._resolve_designator(designator)
            if not resolved:
                print(f"[删除] 未找到 designator={designator} 的映射")
                return
            designator = resolved

            group = self.designator_groups.get(designator, [])
            label = self.designator_map.get(designator)
            if not label and not group:
                return

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            # 删除同组所有对象
            labels_to_delete = set(group) if group else {label}
            print(f"[删除] {designator}: 删除 {len(labels_to_delete)} 个对象")
            for lbl in labels_to_delete:
                for obj in list(doc.Objects):
                    if obj.Label == lbl:
                        try:
                            doc.removeObject(obj.Name)
                        except Exception:
                            pass
                        break

            # 清除映射
            self.designator_map.pop(designator, None)
            for lbl in labels_to_delete:
                self.label_map.pop(lbl, None)
                self.last_positions.pop(lbl, None)
            self.designator_groups.pop(designator, None)

        except Exception as e:
            print(f"删除对象失败: {e}")

    def handle_cross_probe(self, data):
        """EDA → FreeCAD 交叉定位"""
        designator = data.get('designator')
        if not designator:
            return
        self.message_queue.put({
            'type': 'cross_probe',
            'designator': designator
        })

    def do_cross_probe(self, designator):
        """在主线程中定位到指定对象"""
        try:
            import FreeCAD
            import FreeCADGui

            resolved = self._resolve_designator(designator)
            if not resolved:
                print(f"[交叉定位] 未找到 designator={designator} 的映射")
                return
            designator = resolved
            label = self.designator_map.get(designator)
            if not label:
                return

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            obj = None
            for o in doc.Objects:
                if o.Label == label:
                    obj = o
                    break

            if not obj:
                return

            # 选中对象并 fit view
            gui_doc = FreeCADGui.getDocument(doc.Name)
            if gui_doc:
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(obj)

                # Fit view 到选中对象
                try:
                    FreeCADGui.SendMsgToActiveView("ViewFit")
                except Exception as e:
                    print(f"fit view 失败: {e}")

        except Exception as e:
            print(f"交叉定位失败: {e}")

    # ==================== 位置监听（FreeCAD → EDA）====================

    def enable_monitor(self):
        """启动位置监听"""
        if self.monitor_active:
            return
        self.monitor_active = True
        self.snapshot_positions()
        print(f"FreeCAD端位置监听已启动，已记录 {len(self.last_positions)} 个对象初始位置")

    def disable_monitor(self):
        """停止位置监听"""
        self.monitor_active = False
        self.designator_map.clear()
        self.label_map.clear()
        self.designator_groups.clear()
        self.last_positions.clear()
        self.center_offset = {'x': 0, 'y': 0, 'z': 0}
        print("FreeCAD端位置监听已停止，所有映射表已清理")

    def snapshot_positions(self):
        """记录当前所有已映射对象的位置"""
        try:
            import FreeCAD

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            for label in self.label_map:
                for obj in doc.Objects:
                    if obj.Label == label and hasattr(obj, 'Placement'):
                        p = obj.Placement
                        yaw, pitch, roll = p.Rotation.getYawPitchRoll()
                        self.last_positions[label] = {
                            'x': p.Base.x,
                            'y': p.Base.y,
                            'z': p.Base.z,
                            'yaw': yaw,
                            'pitch': pitch,
                            'roll': roll
                        }
                        break
        except Exception as e:
            print(f"[位置快照] 记录位置失败: {e}")

    def check_position_changes(self):
        """检查对象位置变化（由 QTimer 定时调用），只发主对象的通知"""
        if not self.monitor_active or self.last_update_source is not None:
            return

        # 调试日志：首次调用时打印状态
        if not hasattr(self, '_check_debug_printed'):
            self._check_debug_printed = True
            print(f"[位置监听] 监听已激活，label_map有 {len(self.label_map)} 个对象，last_positions有 {len(self.last_positions)} 个快照")

        try:
            import FreeCAD

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            notified = set()  # 避免同一 designator 重复通知
            for label, designator in self.label_map.items():
                if designator in notified:
                    continue
                for obj in doc.Objects:
                    if obj.Label == label and hasattr(obj, 'Placement'):
                        p = obj.Placement
                        yaw, pitch, roll = p.Rotation.getYawPitchRoll()
                        current = {
                            'x': p.Base.x,
                            'y': p.Base.y,
                            'z': p.Base.z,
                            'yaw': yaw,
                            'pitch': pitch,
                            'roll': roll
                        }
                        last = self.last_positions.get(label)
                        if last and not self._position_equal(current, last):
                            # 只用主对象的位置发通知
                            main_label = self.designator_map.get(designator)
                            if label == main_label:
                                # FreeCAD 坐标加上居中偏移，还原为 EDA 坐标（mm）
                                eda_x = current['x'] + self.center_offset['x']
                                eda_y = current['y'] + self.center_offset['y']
                                print(f"[位置监听] {designator}: ({last['x']:.2f}, {last['y']:.2f}) -> ({current['x']:.2f}, {current['y']:.2f}) mm, EDA坐标=({eda_x:.2f}, {eda_y:.2f})")
                                self.send_to_clients({
                                    "type": "position_update_from_freecad",
                                    "designator": designator,
                                    "x": eda_x,
                                    "y": eda_y,
                                    "rotation": yaw
                                })
                                notified.add(designator)
                                self.last_freecad_move_time = time.time()
                            self.last_positions[label] = current
                        break
        except Exception as e:
            print(f"检查位置变化失败: {e}")

    def check_selection_changes(self):
        """检查 FreeCAD 选中对象变化，发送交叉定位到 EDA"""
        if not self.monitor_active:
            return

        try:
            import FreeCADGui

            sel = FreeCADGui.Selection.getSelection()
            current_labels = set()
            for obj in sel:
                if hasattr(obj, 'Label'):
                    current_labels.add(obj.Label)

            # 检测新选中的对象
            new_labels = current_labels - self.last_selected_labels
            for label in new_labels:
                designator = self.label_map.get(label)
                if designator:
                    print(f"[选中监听] FreeCAD选中 {label} -> {designator}，发送交叉定位到EDA")
                    self.send_to_clients({
                        "type": "cross_probe_from_freecad",
                        "designator": designator
                    })

            self.last_selected_labels = current_labels

        except Exception as e:
            print(f"[选中监听] 检查选中变化失败: {e}")

    def check_deleted_objects(self):
        """检查 FreeCAD 中已删除的映射对象，通知 EDA 同步删除"""
        if not self.monitor_active:
            return

        try:
            import FreeCAD

            doc = FreeCAD.ActiveDocument
            if not doc:
                return

            existing_labels = {obj.Label for obj in doc.Objects}

            # 只检查主对象（designator_map 中的 label），辅助对象丢失不影响
            deleted = []
            for designator, main_label in list(self.designator_map.items()):
                if main_label not in existing_labels:
                    deleted.append(designator)

            for designator in deleted:
                main_label = self.designator_map.pop(designator)
                # 清理该 designator 的所有关联数据
                group = self.designator_groups.pop(designator, [])
                for l in group:
                    self.label_map.pop(l, None)
                    self.last_positions.pop(l, None)
                print(f"[删除监听] FreeCAD删除对象 {main_label} -> {designator}，通知EDA删除")
                self.send_to_clients({
                    "type": "delete_from_freecad",
                    "designator": designator
                })

        except Exception as e:
            print(f"[删除监听] 检查删除失败: {e}")

    # ==================== 消息队列处理 ====================

    def process_message_queue(self):
        """处理消息队列中的任务（在FreeCAD主线程中定时调用）"""
        messages = self.message_queue.get_all()

        for msg in messages:
            try:
                msg_type = msg.get('type')

                if msg_type == 'import_step':
                    success = self.import_step_file(msg['file_path'], msg.get('sync', False))
                    result_msg = {
                        "type": "import_complete" if success else "error",
                        "details": "成功导入STEP模型" if success else None,
                        "message": "STEP导入失败" if not success else None
                    }
                    self.send_to_clients(result_msg)

                elif msg_type == 'build_mapping':
                    self.do_build_mapping(msg['components'])

                elif msg_type == 'position_update':
                    self.do_position_update(msg['designator'], msg['x'], msg['y'], msg['rotation'])

                elif msg_type == 'rename_designator':
                    self.do_rename_designator(msg['old'], msg['new'])

                elif msg_type == 'delete_object':
                    self.do_delete_object(msg['designator'])

                elif msg_type == 'cross_probe':
                    self.do_cross_probe(msg['designator'])

                elif msg_type == 'enable_monitor':
                    self.enable_monitor()

                elif msg_type == 'disable_monitor':
                    self.disable_monitor()

            except Exception as e:
                print(f"处理任务失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 清理临时文件
                if msg.get('type') == 'import_step':
                    try:
                        temp_dir = msg.get('temp_dir')
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception as e:
                        print(f"清理临时文件失败: {e}")

    # ==================== 通信工具 ====================

    async def send_error(self, websocket, message):
        try:
            await websocket.send(json.dumps({"type": "error", "message": message}))
        except Exception:
            pass

    def send_to_clients(self, message_dict):
        """从主线程安全地向所有客户端发送消息"""
        if not self.loop:
            print(f"[发送] 失败: event loop 不存在")
            return
        if not self.clients:
            print(f"[发送] 失败: 没有已连接的客户端 (clients为空)")
            return
        try:
            data = json.dumps(message_dict)
            msg_type = message_dict.get('type', '?')
            for client in list(self.clients):
                future = asyncio.run_coroutine_threadsafe(client.send(data), self.loop)
            print(f"[发送] 已提交到event loop: type={msg_type}, 数据长度={len(data)}, 客户端数={len(self.clients)}")
        except Exception as e:
            print(f"发送消息到客户端失败: {e}")
            import traceback
            traceback.print_exc()

    # ==================== 服务器生命周期 ====================

    def start_server(self):
        if self.is_running:
            print("服务器已在运行")
            return

        def run_server():
            try:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                async def create_server():
                    return await websockets.serve(
                        self.register_client,
                        self.host,
                        self.port,
                        max_size=100 * 1024 * 1024
                    )

                self.server = self.loop.run_until_complete(create_server())
                self.is_running = True

                print(f"WebSocket服务器启动成功!")
                print(f"地址: ws://localhost:{self.port}")
                print("等待客户端连接...")

                self.loop.run_forever()
            except OSError as e:
                if "Address already in use" in str(e):
                    print(f"端口 {self.port} 已被占用")
                else:
                    print(f"网络错误: {e}")
                self.is_running = False
            except Exception as e:
                print(f"启动失败: {e}")
                self.is_running = False

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        time.sleep(0.5)

    def stop_server(self):
        """停止WebSocket服务器"""
        if not self.is_running:
            return

        try:
            if self.loop and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self.loop.stop)

            self.is_running = False
            print("WebSocket服务器已停止")
        except Exception as e:
            print(f"停止服务器时出错: {e}")
        finally:
            self.cleanup_resources()

    def cleanup_resources(self):
        """清理资源"""
        try:
            if self.loop and not self.loop.is_closed():
                try:
                    self.loop.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"资源清理失败: {e}")


def is_freecad_environment():
    try:
        import FreeCAD
        return True
    except ImportError:
        return False


server = WebSocketPCBServer()
server.start_server()

if is_freecad_environment():
    print("FreeCAD环境已检测，服务器已启动")
    print("请在嘉立创EDA中点击'连接FreeCAD'")

    # 使用QTimer在FreeCAD主线程中轮询消息队列
    try:
        from PySide2.QtCore import QTimer
    except ImportError:
        try:
            from PySide.QtCore import QTimer
        except ImportError:
            QTimer = None

    if QTimer:
        # 消息队列处理定时器
        timer = QTimer()
        timer.timeout.connect(server.process_message_queue)
        timer.start(100)
        print("已注册主线程定时器（100ms轮询消息队列）")

        # 位置监听定时器（500ms 检查对象位置变化）
        monitor_timer = QTimer()
        monitor_timer.timeout.connect(server.check_position_changes)
        monitor_timer.timeout.connect(server.check_selection_changes)
        monitor_timer.timeout.connect(server.check_deleted_objects)
        monitor_timer.start(500)
        print("已注册位置监听定时器（500ms轮询位置+选中+删除）")
    else:
        print("警告: 无法导入QTimer，导入操作可能无法在主线程中执行")
else:
    print("注意: 未检测到FreeCAD环境，服务器仅接收文件")
    if __name__ == "__main__":
        try:
            while server.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n服务器停止")
            server.stop_server()
