import os
from dataclasses import dataclass
from itertools import product
from rich import print
import sys

GPUS = 5
name = "llama-7b"

@dataclass
class Variant:
    name: str # prompt invariance
    flag: str # --promptinv
    values: list[str] # ["True", "False"]

# models = "--models meta-llama/Llama-2-7b-hf meta-llama/Llama-2-13b-hf EleutherAI/pythia-12b bigscience/bloom-7b1 EleutherAI/pythia-6.9b"
models = "--models huggyllama/llama-7b"
# models = "--models gpt2"
# models = "--models sshleifer/tiny-gpt2"
BURNS_DATASETS = [
    "ag_news",
    "amazon_polarity",
    "dbpedia_14",
    "glue:qnli",
    "imdb",
    "piqa",
    "super_glue:boolq",
    "super_glue:copa",
    "super_glue:rte",
]

datasets = "--datasets " + " ".join(f"'{dataset}'" for dataset in BURNS_DATASETS)
binarize = "--binarize"
num_gpus = f"--num_gpus {GPUS}"

START_NUM = 0

def make_script(variants: list[Variant]) -> str:
    """Return a script that runs a sweep over the given variants."""
    script = f"""#!/bin/bash
#SBATCH --nodes=1
#SBATCH --gpus-per-node={GPUS}
#SBATCH --time=2-0
#SBATCH --partition=single
#SBATCH --job-name=elk_sweep_alpha
"""
    script += "# This script was generated by sweep-script-gen.py\n\n"
    script += f"# {variants}\n\n"
    script += f"# {models}\n"
    script += f"# {datasets}\n"
    script += """
i=0
while [[ -e not-133-sweep-out-$i.txt ]] ; do
    let i++
done
filename="not-133-sweep-out-$i.txt"
exec > $filename 2>&1

j=0
while [[ -e commands_status-$j.csv ]] ; do
    let j++
done
csv_file="commands_status-$j.csv"
echo \"idx,status,command\" > $csv_file
"""
    script += "set -e\n\n"
    script += "# cd ../elk\n"

    combinations = list(product(*[variant.values for variant in variants]))

    commands = []

    combinations = [combo for combo in combinations if not (combo[0] == "eigen" and combo[1] == "burns")]
    combinations = [combo for combo in combinations if not (combo[0] == "eigen" and combo[5] == "ccs_prompt_var")] # does not apply for vinc
    combinations = [combo for combo in combinations if not (combo[0] == "ccs" and combo[4] is not None)] # ccs should not have neg_cov_var
    combinations = [combo for combo in combinations if not (combo[0] == "eigen" and combo[4] is None)] # vinc should not have None, only 0, 0.5, 1
    combinations = [combo for combo in combinations if not (combo[5] == "ccs_prompt_var" and combo[3] is "1")] # doing this throws a Warning Only one variant provided. Prompt variance loss will cause errors.
    print(f"Number of combinations: {len(combinations)}")

    for combo in combinations:
        command = "elk sweep "
        command += models + " " + datasets + " " + binarize + " "
        out_dir = "--name "
        for i, value in enumerate(combo):
            net = combo[1]
            if value is not None:
                if net == "eigen" and variants[i].flag == "--norm":
                    pass
                else:
                    command += f"{variants[i].flag}={value} "
                    out_dir += f"{variants[i].flag[2:]}={value}-"
                if net == "ccs" and variantes[i].flag == "--erase_prompt":
                    # ignore --erase_prompt for CCS for now
                    pass
        command += num_gpus
        commands.append(command)

    script += "commands=( \\\n"
    for command in commands:
        print(command + "\n")
        script += f'"{command}" \\\n'
    script = script[:-2] + "\n)\n\n"

    script += """
idx=0
for command in "${commands[@]}"; do
    echo "$idx,NOT STARTED,$command" >> $csv_file
    ((idx=idx+1))
done
"""

    script += f"""
len=${{#commands[@]}}
for ((idx={START_NUM};idx<len;idx++)); do
    command=${{commands[$idx]}}
    sed -i "s|^$idx,NOT STARTED|$idx,RUNNING|g" $csv_file
    echo "Running command: $command"
    curl -d "Sweep [$idx]: $command" ntfy.sh/derpy
    if ! eval "$command"; then
        sed -i "s|^$idx,RUNNING|$idx,ERROR|g" $csv_file
        echo "Error occurred: Failed to execute command: $command"
        curl -d "Error occurred: Failed to execute command: $command" ntfy.sh/derpy
        break
    else
        sed -i "s|^$idx,RUNNING|$idx,DONE|g" $csv_file
        echo "Command completed successfully: $command"
        curl -d "Command completed successfully: $command" ntfy.sh/derpy
    fi
done
"""

    script += "echo 'All combinations completed.'\n" 

    return script


if __name__ == "__main__":
    variants = [ # do not change order because the order matters
        Variant("net", "--net", ["ccs", "eigen"]),
        Variant("norm", "--norm", ["burns", None]), 
        Variant("per probe prompt", "--probe_per_prompt", ["True", "False"]), # unrestricted
        Variant("prompt indices", "--prompt_indices", [None]), # unrestricted
        Variant("neg_cov_weight", "--neg_cov_weight", [None, 0, 0.5, 1]), # vinc only
        Variant("loss", "--loss", ["ccs_prompt_var", None]), # vinc only
        Variant("erase_prompt", "--erase_prompt", [False, True]),
        Variant("visualize", "--visualize", [True])
    ]

    OUT_FILE = f"sweep-not-291-{name}.sh"
    script = make_script(variants)
    with open(OUT_FILE, "w") as f:
        f.write(script)
    os.system(f"chmod +x {OUT_FILE}")









