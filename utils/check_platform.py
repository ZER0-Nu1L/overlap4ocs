import platform

def is_arm_mac():
    # 获取系统信息
    system = platform.system()
    machine = platform.machine()

    # macOS 的系统名称为 'Darwin'，Arm-based Mac 的机器类型为 'arm64'
    return system == 'Darwin' and machine == 'arm64'

if __name__ == "__main__":
    if is_arm_mac():
        print("This is an Arm-based Mac.")
    else:
        print("This is not an Arm-based Mac.")