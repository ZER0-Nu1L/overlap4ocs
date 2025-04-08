#!/bin/zsh
source ~/.zshrc

# Create necessary directories if they don't exist
if [[ ! -d "config/config_batch" ]]; then
    mkdir -p config/config_batch
fi

if [[ ! -d "logs" ]]; then
    mkdir -p logs
fi

# Extract parameters from the base config for the log filename (comment-aware)
alg=$(grep -E "^\s*algorithm\s*=" config/instance.toml | awk -F'=' '{print $2}' | sed 's/#.*//g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -d '"')
p=$(grep -E "^\s*p\s*=" config/instance.toml | awk -F'=' '{print $2}' | sed 's/#.*//g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
k=$(grep -E "^\s*k\s*=" config/instance.toml | awk -F'=' '{print $2}' | sed 's/#.*//g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
B=$(grep -E "^\s*B\s*=" config/instance.toml | awk -F'=' '{print $2}' | sed 's/#.*//g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# Create the summary log file
summary_log_file="logs/instance_alg=${alg}_p=${p},k=${k},B=${B},m=-.log"

# Array of m values to use
m_values=(32 64 128 256 512 1024)

# Arrays to store extracted values
CCT_one=()
CCT_baseline=()
CCT_ours=()
CCT_ideal=()

# Extract other parameters from the original config file
config_params=$(grep -v "^#" config/instance.toml | grep -v "^ *m *=" | grep "=" | sed 's/^[ \t]*//;s/[ \t]*$//')

# Create config files and run for each m value
for m in ${m_values[@]}; do
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
    if which notify >/dev/null 2>&1; then
        notify -m "instance_${m} finish"
    fi
done

echo "All batch runs completed successfully"

# Extract values from logs
echo "Extracting results from logs..."
for m in ${m_values[@]}; do
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
echo "message_sizes = [${(j: :)m_values}]"
echo "CCT_one = [${(j:, :)CCT_one}]"
echo "CCT_baseline = [${(j:, :)CCT_baseline}]"
echo "CCT_ours = [${(j:, :)CCT_ours}]"
echo "CCT_ideal = [${(j:, :)CCT_ideal}]"

# Write summary to log file with the new naming format
{
    echo "Results Summary:"
    echo "Configuration Parameters:"
    echo "$config_params"
    echo
    echo "message_sizes = [${(j: :)m_values}]"
    echo "CCT_one = [${(j:, :)CCT_one}]"
    echo "CCT_baseline = [${(j:, :)CCT_baseline}]"
    echo "CCT_ours = [${(j:, :)CCT_ours}]"
    echo "CCT_ideal = [${(j:, :)CCT_ideal}]"
} > "${summary_log_file}"

echo "Summary written to ${summary_log_file}"

# Clean up temporary config files
echo "Cleaning up temporary configuration files..."
rm -f config/config_batch/instance_m=*.toml

if which notify >/dev/null 2>&1; then
    notify -m "All instance finish running!"
fi
