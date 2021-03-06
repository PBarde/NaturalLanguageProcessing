import numpy as np
import os
import subprocess
import datetime
import time
import sys
import argparse


def get_base_xp_name_from_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('base_xp_name', type=str, action='store',
                        help="Name of the base experience folder (located in the 'experiences' folder) which we want to improve")
    args = parser.parse_args()
    return args.base_xp_name


def generate_random_search_experience_name(base_xp_name):
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder_name = f"random_search_{base_xp_name}_{now}"
    return folder_name


def parse_config(exp_name):
    exp_config = {}
    f = open(f'experiences/{exp_name}/exp_config.txt', 'r')
    lines = f.readlines()
    f.close()
    for i in lines:
        values = i[:-1].split("    ")
        exp_config[values[0]] = values[1]
    return exp_config


def generate_new_config(base_config, random_search_experience_name, xp_id):
    new_random_config = {}
    for key, value in base_config.items():
        if key in ['batch_size', 'dp_keep_prob', 'emb_size', 'hidden_size', 'initial_lr', 'num_layers', 'seq_len']:
            new_random_value = float(value) + np.random.randn() * float(value) / 2
            if key in ['num_layers']:
                new_random_value = max(1, int(new_random_value))
            if key in ['batch_size', 'emb_size', 'hidden_size', 'seq_len']:
                new_random_value = max(10, int(new_random_value))
            if base_config['model'] == "TRANSFORMER" and key == 'hidden_size':
                nb_heads = 16
                remaining = new_random_value % nb_heads
                if remaining >= nb_heads / 2:
                    new_random_value += nb_heads - remaining
                else:
                    new_random_value -= remaining
                if new_random_value == 0:
                    new_random_value = nb_heads
            if key in ['dp_keep_prob']:
                new_random_value = max(0.1, min(0.9, float(new_random_value)))
            if key in ['initial_lr']:
                new_random_value = max(0.00001, float(new_random_value))
            new_random_config[key] = new_random_value
        elif key in ['model', 'optimizer']:
            new_random_config[key] = value
    new_random_config['save_dir'] = f"{random_search_experience_name}_{xp_id}_"
    new_random_config['save_best'] = ""
    print("generated config:", new_random_config)
    return new_random_config


def start_process_with_config(config):
    command_string = "./ptb-lm.py"
    args = [command_string]
    for key, value in config.items():
        # args.append(f"--{key}={value}")
        args.append(f"--{key}")
        if value != "":
            args.append(f"{value}")
    process = subprocess.Popen(args)
    return process


def monitor_process(process, random_search_experience_name, xp_id, base_ppls):
    time.sleep(30)
    need_to_kill = False
    xp_folder = ""
    search_name = f"{random_search_experience_name}_{xp_id}_"
    for xp in os.listdir("./"):
        if xp.startswith(search_name):
            xp_folder = xp
            break
    if xp_folder == "":
        print("Failed to find folder that starts with:", search_name)
        print("in", os.listdir("./"))
    last_epoch = -1
    while True:
        sys.stdout.flush()
        ppls = parse_log(xp_folder)
        current_epoch = len(ppls) - 1
        if current_epoch != last_epoch:
            last_epoch = current_epoch
            print(f"Epoch {current_epoch}, train ppl: {ppls[current_epoch][0]}, val ppl: {ppls[current_epoch][1]}")
            # Performance check (after 3 epochs, we start checking if the experiment yields better results)
            if current_epoch >= 2:
                if ppls[current_epoch][0] > base_ppls[current_epoch][0] and ppls[current_epoch][1] > base_ppls[current_epoch][1]:
                    print(f"Stopping training because current ppl values did not beat the ones of the base xp "
                          f"(train: {base_ppls[current_epoch][0]}, val: {base_ppls[current_epoch][1]})")
                    need_to_kill = True
                    break
            # Overfitting check (after 6 epochs, we check if the model is overfitting)
            if current_epoch >= 5:  # and ppls[-1][2] > base_ppls[-1][2]:  # but only if not better than the base one
                need_to_kill = True
                for t in range(5):
                    if ppls[current_epoch-t][1] < ppls[current_epoch-5][1]:
                        need_to_kill = False
                        break
                if need_to_kill:
                    print(f"Stopping training because the network is overfitting")
                    break
        if current_epoch == 39:
            break
        time.sleep(30)
    if need_to_kill:
        kill_process(process)


def parse_log(xp_folder):
    if not os.path.isfile(f'{xp_folder}/log.txt'):
        return []

    f = open(f'{xp_folder}/log.txt', 'r')
    lines = f.readlines()
    f.close()
    ppls = []
    for line in lines:
        values = line.split("\t")
        epoch = int(values[0].split("epoch: ")[1])
        train_ppl = float(values[1].split("train ppl: ")[1])
        val_ppl = float(values[2].split("val ppl: ")[1])
        best_val = float(values[3].split("best val: ")[1])
        ppls.append((train_ppl, val_ppl, best_val))
    return ppls


def kill_process(process):
    print("Killing process", process.pid)
    process.kill()


# ========== MAIN ==========
base_xp_name = get_base_xp_name_from_args()
random_search_experience_name = generate_random_search_experience_name(base_xp_name)
base_config = parse_config(base_xp_name)
base_ppls = parse_log(f"experiences/{base_xp_name}")
xp_id = 0
while True:
    xp_id += 1
    print(f"Generating experience {xp_id}")
    new_config = generate_new_config(base_config, random_search_experience_name, xp_id)
    process = start_process_with_config(new_config)
    monitor_process(process, random_search_experience_name, xp_id, base_ppls)
