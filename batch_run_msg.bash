#!/bin/bash

# Create necessary directories if they don't exist
if [ ! -d "config/config_batch" ]; then
    mkdir -p config/config_batch
fi

if [ ! -d "logs" ]; then
    mkdir -p logs
fi

# Array of m values to use
m_values=(32 64 128 256 512 1024)

# Arrays to store extracted values
CCT_one=()
CCT_baseline=()
CCT_ours=()
CCT_ideal=()

# Extract other parameters from the original config file
config_params=$(grep -v "m = " config/instance.toml | grep -v "^#" | grep "=" | sed 's/^[ \t]*//')

# Create config files and run for each m value
for m in "${m_values[@]}"; do
    # Create config file
    config_file="config/config_batch/instance_m=${m}.toml"
    log_file="logs/instance_m=${m}.log"
    
    # Copy original config and replace m value
    cat config/instance.toml | sed "s/m = [0-9]\+\(.*\)/m = ${m}\1/" > "${config_file}"
    
    echo "Running with m=${m}..."
    
    # Start timestamp
    echo "==========================================" > "${log_file}"
    echo "Starting run with m=${m} at $(date)" >> "${log_file}"
    echo "==========================================" >> "${log_file}"
    echo "" >> "${log_file}"
    
    # Run the program and capture output
    python main.py --config "${config_file}" >> "${log_file}" 2>&1
    
    # End timestamp
    echo "" >> "${log_file}"
    echo "==========================================" >> "${log_file}"
    echo "Finished run with m=${m} at $(date)" >> "${log_file}"
    echo "==========================================" >> "${log_file}"
    
    echo "Completed m=${m}"
    
    # Check if notify tool exists and use it
    if command -v notify &> /dev/null; then
        notify -m "instance_${m} finish"
    fi
done

echo "All batch runs completed successfully"

# Extract values from logs
echo "Extracting results from logs..."
for m in "${m_values[@]}"; do
    log_file="logs/instance_m=${m}.log"
    
    # Extract values using grep and awk
    one_val=$(grep "One-shot CCT:" "${log_file}" | awk '{print $3}')
    baseline_val=$(grep "Baseline CCT:" "${log_file}" | awk '{print $3}')
    optimized_val=$(grep "Optimized CCT:" "${log_file}" | awk '{print $3}')
    ideal_val=$(grep "Ideal CCT:" "${log_file}" | awk '{print $3}')
    
    # Add to arrays
    CCT_one+=("$one_val")
    CCT_baseline+=("$baseline_val")
    CCT_ours+=("$optimized_val")
    CCT_ideal+=("$ideal_val")
done

# Display summary
echo "Results Summary:"
echo "Configuration Parameters:"
echo "$config_params"
echo
echo "message_sizes = [${m_values[*]}]"
echo -n "CCT_one = ["
printf "%s, " "${CCT_one[@]}" | sed 's/, $//'
echo "]"
echo -n "CCT_baseline = ["
printf "%s, " "${CCT_baseline[@]}" | sed 's/, $//'
echo "]"
echo -n "CCT_ours = ["
printf "%s, " "${CCT_ours[@]}" | sed 's/, $//'
echo "]"
echo -n "CCT_ideal = ["
printf "%s, " "${CCT_ideal[@]}" | sed 's/, $//'
echo "]"

# Also write summary to log file
{
    echo "Results Summary:"
    echo "Configuration Parameters:"
    echo "$config_params"
    echo
    echo "message_sizes = [${m_values[*]}]"
    echo -n "CCT_one = ["
    printf "%s, " "${CCT_one[@]}" | sed 's/, $//'
    echo "]"
    echo -n "CCT_baseline = ["
    printf "%s, " "${CCT_baseline[@]}" | sed 's/, $//'
    echo "]"
    echo -n "CCT_ours = ["
    printf "%s, " "${CCT_ours[@]}" | sed 's/, $//'
    echo "]"
    echo -n "CCT_ideal = ["
    printf "%s, " "${CCT_ideal[@]}" | sed 's/, $//'
    echo "]"
} > logs/instance_summary.log

echo "Summary written to logs/instance_summary.log"

if command -v notify &> /dev/null; then
    notify -m "All instance finish running!"
fi