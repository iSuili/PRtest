# -*- coding: utf-8 -*-
import os
import time
import numpy as np
import random
import argparse
import torch
from trainer import ModelTrainer
import logging
from client import Client
from server import Server
from utils.data_utils import load_ratings_dataset
from utils.io_utils import save_config, ensure_dir
from fl import run_fl
import secretflow as sf

def arg_parse():
    parser = argparse.ArgumentParser()

    # Dataset part
    parser.add_argument(dest="domains", metavar="domains", nargs="*",default=["Food","Kitchen"],
                        help="Food Kitchen")
    parser.add_argument("--load_prep", dest="load_prep", action="store_true",
                        default=True,
                        help="Whether need to load preprocessed the data. If "
                        "you want to load preprocessed data, add it")
    # Training part
    parser.add_argument("--method", type=str, default="FedP2FCDR",
                        help="method")
    parser.add_argument("--log_dir", type=str,
                        default="log", help="directory of logs")
    parser.add_argument("--cuda", type=bool, default=torch.cuda.is_available())
    parser.add_argument("--num_round", type=int, default=15,
                        help="Number of total training rounds.")
    parser.add_argument("--local_epoch", type=int, default=3,
                        help="Number of local training epochs.")
    parser.add_argument("--optimizer", choices=["sgd", "adagrad", "adam",
                                                "adamax"], default="adam",
                        help="Optimizer: sgd, adagrad, adam or adamax.")
    parser.add_argument("--lr", type=float, default=0.001,
                        help="Applies to sgd and adagrad.")  # 0.001
    parser.add_argument("--lr_decay", type=float, default=0.9,
                        help="Learning rate decay rate.")
    parser.add_argument("--weight_decay", type=float, default=5e-4,
                        help="Weight decay (L2 loss on parameters).")
    parser.add_argument("--batch_size", type=int,
                        default=1024, help="Training batch size.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--eval_interval", type=int,
                        default=1, help="Interval of evalution")
    parser.add_argument("--frac", type=float, default=1,
                        help="Fraction of participating clients")
    parser.add_argument("--mu", type=float, default=0,
                        help="hyper parameter for FedProx")
    parser.add_argument("--checkpoint_dir", type=str,
                        default="checkpoint", help="Checkpoint Dir")
    parser.add_argument("--model_id", type=str, default=str(int(time.time())),
                        help="Model ID under which to save models.")
    parser.add_argument("--do_eval", action="store_true")
    parser.add_argument("--es_patience", type=int,
                        default=5, help="Early stop patience.")
    parser.add_argument("--ld_patience", type=int, default=1,
                        help="Learning rate decay patience.")


    args = parser.parse_args()
    assert (args.method in [ "FedP2FCDR"])
    return args


def seed_everything(args):
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    os.environ["PYTHONHASHSEED"] = str(args.seed)
    if args.cuda:
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"


def init_logger(args):
    """Init a file logger that opens the file periodically and write to it.
    """
    log_path = os.path.join(args.log_dir,
                            "domain_" + "".join([domain[0] for domain
                                                 in args.domains]))
    ensure_dir(log_path, verbose=True)

    model_id = args.model_id if len(args.model_id) > 1 else "0" + args.model_id
    log_file = os.path.join(log_path, args.method + "_" + model_id + ".log")

    logging.basicConfig(
        format="%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.warning,
        filename=log_file,
        filemode="w+"
    )

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    formatter = logging.Formatter("%(asctime)s | %(message)s")
    console.setFormatter(formatter)
    logging.getLogger("").addHandler(console)


def main():
    args = arg_parse()
    seed_everything(args)
    init_logger(args)
    train_datasets, valid_datasets, test_datasets = load_ratings_dataset(args)
    # Save the config of input arguments
    save_config(args)
    clients = []
    sf.shutdown()
    sf.init(["alice", "bob", "server"], address='local', num_gpus=1)
    alice_pyu = sf.PYU("alice")
    bob_pyu = sf.PYU("bob")
    server_pyu = sf.PYU("server")
    Client0 = Client(ModelTrainer, 0, args,
                        train_datasets, valid_datasets,
                        test_datasets,device=alice_pyu)
    Client1 = Client(ModelTrainer, 1, args,
                    train_datasets, valid_datasets,
                    test_datasets,device=bob_pyu)
    clients = [Client0, Client1]           

    server = Server(args, device=server_pyu)

    run_fl(clients, server, args)


if __name__ == "__main__":
    main()