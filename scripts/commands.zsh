scp -r 'server12:/home/sdn/wcb/overlap4ocs/logs/instance_alg*' ./logs
scp -r 'server13:/home/sdn/wcb/overlap4ocs/logs/instance_alg*' ./logs
scp -r 'server14:/home/sdn/wcb/overlap4ocs/logs/instance_alg*' ./logs

scp -r 'server12:/home/sdn/wcb/overlap4ocs/logs' ./logs

scp -r 'server12:/home/sdn/wcb/overlap4ocs/config/matrix/' ./config/matrix/* 
---
k4_p16_sweep_msg-stride4_matrix.toml

example_matrix_sweep_msg+k.toml

PYTHONPATH=. python scripts/generate_matrix_configs.py --matrix config/matrix/example_matrix_sweep_msg+k.toml --overwrite


PYTHONPATH=. python scripts/matrix_runner.py --matrix config/matrix/example_matrix_sweep_msg+k.toml
