# SO-ARM101 跟随延迟测试

在已经完成标定的 SO-ARM101 上，用 LeRobot 0.7.0 测量主从跟随延迟。默认六个关节同时跟随，每帧记录主机时间戳，结束后按关节给出延迟。不需要相机。先退出正在运行的 lerobot-teleoperate。

## 推荐：在 Windows 上直接运行

usbipd 把 USB 转发进 WSL 时会让串口读取偶尔卡住（实测 p99 13–18 ms，最长 60 ms 以上，偶尔超时 50 ms），在 Windows 上直接读则 p99 约 1.5 ms。实时控制、遥操作和录制数据建议在 Windows 上跑，训练可以继续放在 WSL 或云端。

一次性准备：在 Windows 上安装 Miniforge，创建 Python 3.12 的 lerobot 环境，安装与显卡驱动匹配的 CUDA 版 PyTorch，再安装 lerobot[feetech]==0.7.0。把标定文件从 WSL 的 ~/.cache/huggingface/lerobot/calibration/ 复制到 Windows 的 %USERPROFILE%\.cache\huggingface\lerobot\calibration\，目录结构保持一致。

使用前先把两块板从 WSL 还给 Windows（BUSID 以 usbipd list 为准），然后用 COM 口运行：

    usbipd detach --busid 2-1
    usbipd detach --busid 2-3
    .\start.ps1 --leader-port COM5 --follower-port COM4 --hz 60

start.ps1 默认使用 %USERPROFILE%\miniforge3 下的 lerobot 环境，可用 SO101_CONDA_ROOT 或 SO101_CONDA_ENV 修改。如果 PowerShell 拒绝运行脚本，用 powershell -ExecutionPolicy Bypass -File .\start.ps1 ...。要回到 WSL，再运行 attach-wsl.ps1。

## 接入 WSL

在 PowerShell 运行 usbipd list，确认两块 CH343（1a86:55d3）的 BUSID。还没共享的设备需要在管理员 PowerShell 里运行一次 usbipd bind --busid 对应的BUSID。之后用 attach-wsl.ps1 挂接。BUSID 请替换成 usbipd list 的实际值，重新插拔后可能变化：

    .\attach-wsl.ps1 -LeaderBusId 2-3 -FollowerBusId 2-1

在 WSL 里用 /dev/serial/by-id/ 下的路径指定端口。它包含板子的序列号，不随挂接顺序变化。ttyACM 编号和 usbipd 下的 by-path 都只反映挂接顺序，容易认错。

    ls -l /dev/serial/by-id/

## 运行

在 Ubuntu 中进入本目录：

    source "$HOME/miniforge3/etc/profile.d/conda.sh" && conda activate lerobot
    python measure_latency.py \
      --leader-port   /dev/serial/by-id/usb-1a86_USB_Single_Serial_<leader序列号>-if00 \
      --follower-port /dev/serial/by-id/usb-1a86_USB_Single_Serial_<follower序列号>-if00 \
      --hz 30

也可以用 bash start.sh 加相同参数，它会自动激活环境。如安装位置或环境名不同，可设置 SO101_CONDA_INIT 或 SO101_CONDA_ENV。

从臂空载，清空工作区，两臂放在相近的静止姿态。核对端口后输入 START。连接从臂会使舵机进入保持状态，退出后舵机会失去保持力，确保从臂有支撑并让手远离夹爪。按 Enter 后先静止约一秒，再像平时遥操作一样移动主臂，持续到结束（默认 15 秒）。Ctrl+C 可提前停止，已采到的数据仍会保存和分析。

常用参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| --joints | 全部六个 | 参与跟随的关节，其余保持起始位置，例如 --joints shoulder_pan elbow_flex |
| --hz | 30 | 控制频率，最大 60 |
| --seconds | 15 | 采样时长，3–120 |
| --p-coefficient | 32 | 连接时写入从臂的位置环 P 增益，1–32。LeRobot 默认 16。Windows 直连实测 P=32、D=32 比默认快约 30 ms 且不抖；在 WSL（usbipd）下 P=32 会抖，WSL 中用 24 |
| --i-coefficient | LeRobot 默认 0 | 连接时写入从臂的位置环 I 增益，0–16 |
| --d-coefficient | LeRobot 默认 32 | 连接时写入从臂的位置环 D 增益，0–96 |

P、I、D 只在本脚本连接时写入。下次用 lerobot-teleoperate 连接会写回 LeRobot 的值，除非加上 --robot.position_p_coefficient / --robot.position_i_coefficient / --robot.position_d_coefficient。CSV 文件名会记录频率和 PID，例如 latency-…-60hz-p24-i0-d32.csv。

和 lerobot-teleoperate 一样，没有速度和行程限制，主臂动多快从臂就收到多快的指令。唯一的区别是使用相对起始位置映射：从臂目标 = 从臂起点 + (主臂当前 − 主臂起点)，避免两臂初始角度差在连接瞬间变成跳变。这只带来一个固定偏差，不影响延迟。两臂起始姿态要尽量一致，否则从臂会带着这个偏差运动，可能先于主臂碰到机械限位。

## 读结果

每次运行在 results/ 下生成一个 CSV，并在终端打印分析。已有的 CSV 可以随时重新分析：

    python analyze_latency.py results/latency-XXXX.csv

- 控制周期和总线调用：每帧依次读主臂、写从臂目标、读从臂反馈，与 lerobot-teleoperate 每帧的总线操作数量相同（原版也会读一次从臂）。写调用耗时是主机计时，不代表舵机已开始移动。
- 时间戳：一次 sync_read 读出所有关节，所以同一帧里所有关节的时间戳相同。读位置用读调用的起止中点作为采样时刻，目标用写调用返回的时刻。关节之间的延迟差异来自舵机本身（负载、重力、摩擦），而不是通信。
- 每个关节的延迟：把两条完整曲线平移对齐，找误差最小的时间偏移（去掉固定偏差）。L->sent 只包含主机处理时间，应接近 0（旧版 CSV 中包含软件限速），sent->F 是通信、舵机跟踪和反馈采样，L->F 是总的跟随延迟。分辨率受采样周期约束，标 ! 表示达到搜索上限，不可靠。
- err rms / err max：同一时刻主臂请求值与从臂实际值之差。
- range 小于 3 度的关节视为没动，不计算延迟。夹爪单位是行程的 0–100 %，不是度。
- CSV 每行包含五个时间戳，以及每个关节的 leader、requested、sent、follower 四列（旧版还有 limited 列）。
- 比较不同条件时每种做几次：--hz 30 与 60，以及不同的 --p-coefficient。提高 P 可能减小延迟，也可能引起从臂抖动，从小步开始并观察。
