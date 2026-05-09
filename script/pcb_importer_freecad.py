#!/usr/bin/env python3
"""
PCB FreeCAD导入器 - WebSocket服务器

使用方法:
1. 在FreeCAD中打开宏编辑器
2. 复制此脚本内容到宏编辑器
3. 运行宏启动WebSocket服务器
4. 在嘉立创EDA中点击"连接FreeCAD"
5. 点击"导出到FreeCAD"发送PCB STEP文件

FreeCAD相关：
点击：视图 → 面板 → 报告视图 可以查看脚本运行日志

服务器地址: ws://localhost:8766
"""

import sys
import os
import subprocess

def get_python_executable():
    """获取正确的Python解释器路径（FreeCAD中sys.executable指向FreeCAD.exe）"""
    # sys.executable 如果是python则直接使用
    if 'python' in os.path.basename(sys.executable).lower():
        return sys.executable

    # 在FreeCAD安装目录下查找python.exe
    freecad_dir = os.path.dirname(sys.executable)
    for name in ('python3.exe', 'python.exe', 'python'):
        candidate = os.path.join(freecad_dir, name)
        if os.path.isfile(candidate):
            return candidate

    # bin子目录
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
import threading
import tempfile
import shutil
import queue
import time

class MessageQueue:
    """线程安全的消息队列，用于将任务从WebSocket线程传递到主线程"""

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
        print(f"初始化WebSocket服务器 {host}:{port}")

    async def register_client(self, websocket, path=None):
        self.clients.add(websocket)
        try:
            client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        except Exception:
            client_addr = "unknown"

        print(f"客户端连接: {client_addr}")

        # 与TS端 handleFreeCADMessage 中的 case 'connection_confirmed' 对应
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
            else:
                print(f"未知消息类型: {message_type}")

        except json.JSONDecodeError:
            await self.send_error(websocket, "无效的JSON消息")
        except Exception as e:
            await self.send_error(websocket, f"消息处理错误: {str(e)}")

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

            # 将导入任务放入消息队列，由主线程处理
            import_task = {
                'type': 'import_step',
                'file_path': temp_file_path,
                'temp_dir': temp_dir,
                'filename': filename,
            }
            self.message_queue.put(import_task)

        except Exception as e:
            await self.send_error(websocket, f"文件处理错误: {str(e)}")

    def import_step_file(self, file_path):
        """在主线程中调用，导入STEP文件到FreeCAD"""
        try:
            import FreeCAD
            import ImportGui

            print(f"导入STEP文件: {file_path}")

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
                print("未找到可计算包围盒的对象")
                return

            cx = (bb_min_x + bb_max_x) / 2
            cy = (bb_min_y + bb_max_y) / 2
            cz = (bb_min_z + bb_max_z) / 2
            print(f"模型包围盒中心: ({cx:.2f}, {cy:.2f}, {cz:.2f})")

            if abs(cx) < 0.01 and abs(cy) < 0.01 and abs(cz) < 0.01:
                print("模型已居中，无需移动")
                return

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

    def process_message_queue(self):
        """处理消息队列中的任务（在FreeCAD主线程中定时调用）"""
        messages = self.message_queue.get_all()

        for msg in messages:
            try:
                if msg['type'] == 'import_step':
                    success = self.import_step_file(msg['file_path'])
                    if not success:
                        print(f"STEP导入失败: {msg['filename']}")
            except Exception as e:
                print(f"处理导入任务失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 清理临时文件
                try:
                    temp_dir = msg.get('temp_dir')
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    print(f"清理临时文件失败: {e}")

    async def send_error(self, websocket, message):
        try:
            await websocket.send(json.dumps({"type": "error", "message": message}))
        except Exception:
            pass

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
        timer = QTimer()
        timer.timeout.connect(server.process_message_queue)
        timer.start(100)
        print("已注册主线程定时器（100ms轮询）")
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
