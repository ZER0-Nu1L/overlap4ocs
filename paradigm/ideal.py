from config import get_parameters
import pyperclip

def compute_ideal_time(params):
    B = params['B']
    k = params['k']    
    m_i = params['m_i']
    num_steps = params['num_steps']
    CCT = sum(m_i[i] / B / k for i in range(1, num_steps + 1))
    return CCT

if __name__ == "__main__":
    params = get_parameters()
    CCT = compute_ideal_time(params)
    print(CCT)
    pyperclip.copy(f"{CCT:.2f}")