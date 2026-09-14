# SPI 控制器自动休眠对照测试（尚未应用）

2026-09-14。用户确认恢复的原版iptsd 3.1.0+sl7.1在连续快速物理点击后也出现停顿和约10次重复点击。因此停顿并非只在点击修复候选下发生；这不代表已定位根因，也不代表候选完整可靠性验收已通过。

现场：原服务active，进程阻塞在hidraw_read；SPI ready，错误0、复位0，IRQ41640暂不增长，GPIO3中断线高（未断言），GPIO65供电保持高。随后用户确认运动和震感自行恢复；只读观察收到3342个HID包，IRQ随之增长，全程没有重启iptsd、切换驱动或修改任何设备状态。

当前控制器在空闲250ms后运行时休眠。为测试休眠/唤醒是否参与停顿，拟只把真实88c000.spi控制器power/control从auto改on，保持180秒后自动恢复auto。仍用原版iptsd、原校准和轻触点击，不更改模块、GPIO、Secure Boot或启动项。此操作尚未执行，需用户批准。

`python3 runtime-pm-trial.py`只读预检，已通过。批准后运行`sudo -n python3 runtime-pm-trial.py --apply`，脚本先安排自动恢复，再把控制器保持唤醒；不重启iptsd。若需提前恢复：`sudo python3 /run/sl7-spi-runtime-pm-trial/trial.py --restore`。脚本限定具体设备树、控制器和触控板，动态识别hidraw编号。

同时用passive-health.py记录报告ID计数、中断和控制器状态；用户按能复现问题的节奏正常点击并滑动，出现无响应及时反馈。此轮原版仍可能重复点击，主要评价设备停顿。一次未复现不足以证明因果；若保持active仍停顿，则不能仅归咎于这项自动休眠。不要擅自增加复位/保活命令。
