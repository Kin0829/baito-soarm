# SO-ARM101 跟随延迟测试

在已经完成标定的 SO-ARM101 上，用 LeRobot 0.7.0 测量一个关节的主从跟随。不需要相机。先退出正在运行的 lerobot-teleoperate。

## 接入 WSL

在 PowerShell 运行 usbipd list。必要时分别插拔确认两块 CH343 的 BUSID。还没共享的设备需要在管理员 PowerShell 里运行一次 usbipd bind --busid 对应的BUSID。之后可用 attach-wsl.ps1 自动挂接两块已共享的板。BUSID 请替换成 usbipd list 的实际值：

    .\attach-wsl.ps1 -LeaderBusId 2-1 -FollowerBusId 2-3

用逐个插拔或逐个挂接确认两块板对应的 Linux 设备。ttyACM 编号可能变化。也可以传入已确认的 /dev/serial/by-path/ 路径。

## 运行

在 Ubuntu 中进入本目录。下面的端口是示例，请以本次实际映射为准。

    bash start.sh --leader-port /dev/ttyACM0 --follower-port /dev/ttyACM1 --hz 30

启动脚本会加载 Miniforge、激活 lerobot 环境，并复用此前保存的 so101_leader 和 so101_follower 标定。如安装位置或环境名不同，可设置 SO101_CONDA_INIT 或 SO101_CONDA_ENV。

从臂空载，清空工作区，两臂放在远离机械限位的静止姿态。核对端口后输入 START。连接从臂可能使舵机进入保持状态，退出后舵机可能失去保持力，确保从臂有支撑并让手远离夹爪。按 Enter 后先静止约一秒，再用手把主臂默认测试关节 shoulder_pan（底座）向一个方向移动约 8° 并保持到结束。其余关节保持开始时的位置。Ctrl+C 可停止。

## 读结果

- 控制周期统计包含主臂读、目标写、从臂额外反馈读和循环等待。反馈读会增加负担，因此本脚本的频率不等同于原始遥操作的频率。
- 写调用耗时是主机计时，不代表舵机已开始移动。
- 以起点为基准匹配同方向首次 2° 跨阈值。leader -> sent 包含软件限速影响，sent -> follower 包含通信、舵机跟踪以及反馈采样影响。用 host 读写完成时刻和线性插值估算，分辨率受实际采样周期约束。
- CSV 包含原始时间、Leader 角度、映射后请求目标、实际下发目标、Follower 回读角度和限幅标记。使用相对起始位置映射，避免初始两臂角度差异直接变成跳变指令。
- 将 --hz 改为 60，用相同关节重复测试。每个频率做几次，比较实际频率、帧间隔和跨阈值延迟。限速标记较多时，适当放慢手动动作。
