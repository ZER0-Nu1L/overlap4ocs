import platform

def is_arm_mac():
    # Obtain system information
    system = platform.system()
    machine = platform.machine()

    return system == 'Darwin' and machine == 'arm64'

if __name__ == "__main__":
    if is_arm_mac():
        print("This is an Arm-based Mac.")
    else:
        print("This is not an Arm-based Mac.")