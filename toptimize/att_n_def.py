
# For run in runs:
#   Load model in (Base, Ours)
#       Attack Topology
#       Train Base
#       Train Ours
#   Eval Base vs Ours in Baseline Attack
#   Eval Base vs Ours in Ours Attack
# Done
#
# Compare GCN vs Ours
# ---------------------------------------------------------------------------------------------------------------------------------------
# |       |                  Cora                   |                Cistseer                 |                 Pubmed                  |
# ---------------------------------------------------------------------------------------------------------------------------------------
# |       | Base Attack | Ours Attack |  Cold Start | Base Attack | Ours Attack |  Cold Start | Base Attack | Ours Attack |  Cold Start |
# ---------------------------------------------------------------------------------------------------------------------------------------
# |       |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |  GCN | Ours |
# ---------------------------------------------------------------------------------------------------------------------------------------
# | Run 0 |  70  |  80  |  70  |  80  |  60  |  70  |  70  |  80  |  70  |  80  |  60  |  70  |  70  |  80  |  70  |  80  |  60  |  70  |
# ---------------------------------------------------------------------------------------------------------------------------------------
# | Run 1 |  70  |  80  |  70  |  80  |  60  |  70  |  70  |  80  |  70  |  80  |  60  |  70  |  70  |  80  |  70  |  80  |  60  |  70  |
# ---------------------------------------------------------------------------------------------------------------------------------------
# |  ...  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |  ..  |
# ---------------------------------------------------------------------------------------------------------------------------------------
# | Runs  | 70+1 | 80+1 | 70+1 | 80+1 | 60+1 | 70+1 | 70+1 | 80+1 | 70+1 | 80+1 | 60+1 | 70+1 | 70+1 | 80+1 | 70+1 | 80+1 | 60+1 | 70+1 |
# ---------------------------------------------------------------------------------------------------------------------------------------
import argparse
from numpy.lib.function_base import append
import torch
import torch.nn.functional as F
from torch_geometric.nn import GCN4ConvSIGIR, GAT4ConvSIGIR
from torch_geometric.utils.sparse import dense_to_sparse
from torch_geometric.utils import to_dense_adj
import wandb
import random
import numpy as np
from pathlib import Path
from utils import (
    safe_remove_dir,
    load_data,
    log_dataset_stat,
    log_model_architecture,
    log_step_perf,
    log_run_perf,
    log_hyperparameters,
    cold_start,
    superprint,
    eval_metric,
    log_run_metric,
    pgd_attack,
)
from trainer import Trainer
from model import GCN, GAT, OurGCN, OurGAT
from utils import evaluate_experiment

parser = argparse.ArgumentParser()
parser.add_argument('exp_alias', type=str)
parser.add_argument('-b', '--basemodel', default='GCN', type=str)
parser.add_argument('-d', '--dataset', default='Cora', type=str)
parser.add_argument('-tr', '--total_run', default=2, type=int)
parser.add_argument('-ts', '--total_step', default=5, type=int)
parser.add_argument('-te', '--total_epoch', default=300, type=int)
parser.add_argument('-s', '--seed', default=0, type=int)
parser.add_argument('-hs', '--hidden_sizes', default=None, type=int)
parser.add_argument('-l1', '--lambda1', default=1, type=float)
parser.add_argument('-l2', '--lambda2', default=10, type=float)
parser.add_argument('-t', '--tau', default=10, type=float)
parser.add_argument('-n', '--beta', default=-3, type=float)
parser.add_argument('-csr', '--cold_start_ratio', default=1.0, type=float)
parser.add_argument('-ptb', '--ptb_rate', default=0.05, type=float)
parser.add_argument('-et', '--eval_topo', action='store_true')
parser.add_argument('-le', '--use_last_epoch', action='store_true')
parser.add_argument('-o', '--use_loss_epoch', action='store_true')
parser.add_argument('-de', '--drop_edge', action='store_true')
parser.add_argument('-wnb', '--use_wnb', action='store_true')
parser.add_argument('-gdc', '--use_gdc', action='store_true',
                    help='Use GDC preprocessing for GCN.')
parser.add_argument('-z', '--use_metric', action='store_true')
parser.add_argument('-sm', '--save_model', action='store_true')
args = parser.parse_args()

exp_alias = args.exp_alias
dataset_name = args.dataset
basemodel_name = args.basemodel
total_run = args.total_run
total_step = args.total_step
total_epoch = args.total_epoch
seed = args.seed
hidden_sizes = args.hidden_sizes
lambda1 = args.lambda1
lambda2 = args.lambda2
alpha = args.tau
beta = args.beta
eval_topo = args.eval_topo
cold_start_ratio = args.cold_start_ratio
use_last_epoch = args.use_last_epoch
use_loss_epoch = args.use_loss_epoch
use_wnb = args.use_wnb
drop_edge = args.drop_edge
use_gdc = args.use_gdc
use_metric = args.use_metric
save_model = args.save_model
ptb_rate = args.ptb_rate

# random.seed(seed)
# torch.manual_seed(seed)
# torch.cuda.manual_seed(seed)
# np.random.seed(seed)
# torch.backends.cudnn.deterministic = True
# torch.backends.cudnn.benchmark = False
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


cur_dir = Path(__file__).resolve().parent
exp_name = exp_alias + '_' + dataset_name + '_' + basemodel_name
exp_dir = (cur_dir.parent / 'experiment' / exp_name).resolve()


for attack_name in ['attack_base', 'attack_ours']:

    attack_dir = (cur_dir.parent / 'experiment/attack' /
                  exp_name / attack_name).resolve()
    attack_dir.mkdir(mode=0o777, parents=True, exist_ok=True)
    safe_remove_dir(attack_dir)

    base_vals, base_tests = [], []
    our_vals, our_tests = [], []
    noen_our_vals, noen_our_tests = [], []
    if use_metric:
        all_run_metric = []

    for run in list(range(total_run)):
        # Directories
        run_name = 'run_' + str(run)
        run_dir = exp_dir / ('run_' + str(run))
        attack_run_dir = attack_dir / ('run_' + str(run))
        confmat_dir = attack_run_dir / 'confmat'
        topofig_dir = attack_run_dir / 'topofig'
        tsne_dir = attack_run_dir / 'tsne'
        metric_dir = run_dir / 'metric'
        attack_run_dir.mkdir(mode=0o777, parents=True, exist_ok=True)
        confmat_dir.mkdir(mode=0o777, parents=True, exist_ok=True)
        topofig_dir.mkdir(mode=0o777, parents=True, exist_ok=True)
        tsne_dir.mkdir(mode=0o777, parents=True, exist_ok=True)
        metric_dir.mkdir(mode=0o777, parents=True, exist_ok=True)

        # Path
        dataset_path = (Path(__file__) / '../../data').resolve() / dataset_name
        hyper_path = attack_dir / 'hyper.txt'
        datastat_path = attack_run_dir / 'data_stat.txt'
        archi_path = attack_dir / 'model_archi.txt'
        trainlog_path = attack_run_dir / 'train_log.txt'
        step_perf_path = attack_run_dir / 'step_perf.txt'
        run_perf_path = attack_dir / 'run_perf.txt'
        gradlog_path = attack_run_dir / 'grad_fig.pdf'
        metric_fig_path = metric_dir / 'metric.png'
        metric_txt_path = metric_dir / 'metric.txt'

        log_hyperparameters(args, hyper_path)

        # Dataset
        dataset, data = load_data(dataset_path, dataset_name, device, use_gdc)
        orig_adj = to_dense_adj(data.edge_index, edge_attr=data.edge_attr)
        node_degree = orig_adj.sum(dim=1)[0]
        ################## Attack Model ###################
        # data.edge_index = cold_start(data.edge_index, ratio=cold_start_ratio)
        modified_adj = pgd_attack(
            run_dir, dataset, attack_name, basemodel_name, alpha, trainlog_path, device=device,
            gradlog_path=gradlog_path, ptb_rate=ptb_rate)
        data.edge_index, data.edge_attr = dense_to_sparse(modified_adj)
        print('Finished Attack')
        input()
        ###############  End of Attack Model ##############
        label = data.y
        one_hot_label = F.one_hot(data.y).float()
        adj = to_dense_adj(data.edge_index, max_num_nodes=data.num_nodes)[0]
        gold_adj = torch.matmul(one_hot_label, one_hot_label.T)
        log_dataset_stat(data, dataset, datastat_path)
        ##################################################
        ############## Training Base Model ###############
        ##################################################

        step = 0

        if basemodel_name == 'GCN':
            hidden_sizes = hidden_sizes if hidden_sizes else 16
            model = GCN(dataset.num_features, hidden_sizes,
                        dataset.num_classes).to(device)
            optimizer = torch.optim.Adam([
                dict(params=model.conv1.parameters(), weight_decay=5e-4),
                dict(params=model.conv2.parameters(), weight_decay=0)
            ], lr=0.01)
        else:
            hidden_sizes = hidden_sizes if hidden_sizes else 8
            model = GAT(dataset.num_features, hidden_sizes,
                        dataset.num_classes).to(device)
            optimizer = torch.optim.Adam(
                model.parameters(), lr=0.005, weight_decay=0.0005)
        log_model_architecture(step, model, optimizer,
                               archi_path, overwrite=True)

        trainer = Trainer(model, data, device,
                          trainlog_path, optimizer=optimizer)
        print('Baselike trainer.edge_index',
              trainer.edge_index, trainer.edge_index.shape)
        input()

        if basemodel_name == 'GCN':
            train_acc, val_acc, test_acc = trainer.fit(
                step, 200, lambda1, lambda2, use_last_epoch=False, use_loss_epoch=False)
        else:
            train_acc, val_acc, test_acc = trainer.fit(
                step, 300, lambda1, lambda2, use_last_epoch=False, use_loss_epoch=False)
        base_vals.append(val_acc)
        base_tests.append(test_acc)

        trainer.save_model(run_dir / ('model_'+str(step)+'.pt'), data)

        if eval_topo:
            final, logit = trainer.infer()
            perf_stat = evaluate_experiment(
                step, final, label, adj, gold_adj, confmat_dir, topofig_dir, tsne_dir)

        ##################################################
        ############## Training Our Model ################
        ##################################################

        step_vals, step_tests = [], []
        step_noen_vals, step_noen_tests = [], []
        wnb_group_name = exp_alias + '_run' + \
            str(run) + '_' + wandb.util.generate_id()

        if use_metric:
            all_step_new_edge = None

        for step in range(1, total_step + 1):
            teacher = trainer.checkpoint['logit']
            if eval_topo:
                prev_stat = perf_stat

            wnb_run = None
            if use_wnb:
                wnb_run = wandb.init(
                    project="toptimize", name='Step'+str(step), group=wnb_group_name, config=args)
                wnb_run.watch(model, log='all')

            if basemodel_name == 'GCN':
                hidden_sizes = hidden_sizes if hidden_sizes else 16
                model = OurGCN(dataset.num_features, hidden_sizes,
                               dataset.num_classes, alpha=alpha, beta=beta).to(device)
                optimizer = torch.optim.Adam([
                    dict(params=model.conv1.parameters(), weight_decay=5e-4),
                    dict(params=model.conv2.parameters(), weight_decay=0)
                ], lr=0.01)
                link_pred = GCN4ConvSIGIR
            else:
                hidden_sizes = hidden_sizes if hidden_sizes else 8
                model = OurGAT(dataset.num_features, hidden_sizes,
                               dataset.num_classes, alpha=alpha, beta=beta).to(device)
                print('Our model model.parameters()', model.parameters())
                input()
                optimizer = torch.optim.Adam(
                    model.parameters(), lr=0.005, weight_decay=5e-4)
                link_pred = GAT4ConvSIGIR
            log_model_architecture(step, model, optimizer, archi_path)

            trainer = Trainer(model, data, device,
                              trainlog_path, optimizer)
            noen_train_acc, noen_val_acc, noen_test_acc = trainer.fit(
                step, total_epoch, lambda1, lambda2, link_pred=link_pred, teacher=teacher, use_last_epoch=use_last_epoch, use_loss_epoch=use_loss_epoch, wnb_run=wnb_run)

            step_noen_vals.append(noen_val_acc)
            step_noen_tests.append(noen_test_acc)
            superprint(
                f'Non Ensembled Train {noen_train_acc} Val {noen_val_acc} Test {noen_test_acc}', trainlog_path)

            data.edge_index, data.edge_attr, adj, new_edge = trainer.augment_topology(
                drop_edge=drop_edge)
            if use_metric:
                all_step_new_edge = new_edge.clone().detach() if all_step_new_edge is None else torch.cat([
                    all_step_new_edge, new_edge], dim=1)

            trainer.save_model(
                attack_run_dir / ('model_'+str(step)+'.pt'), data)
            train_acc, val_acc, test_acc = trainer.ensemble(attack_run_dir)

            if eval_topo:
                perf_stat = evaluate_experiment(
                    step, final, label, adj, gold_adj, confmat_dir, topofig_dir, tsne_dir, prev_stat)
            superprint(
                f'Ensembled Train {train_acc} Val {val_acc} Test {test_acc}', trainlog_path)

            step_vals.append(val_acc)
            step_tests.append(test_acc)

            if use_wnb:
                if eval_topo:
                    wnb_run.log(perf_stat)
                    for key, val in perf_stat.items():
                        wandb.run.summary[key] = val
                wandb.run.summary['train_acc'] = train_acc
                wandb.run.summary['val_acc'] = val_acc
                wandb.run.summary['test_acc'] = test_acc
                wandb.finish()

            print()

        our_vals.append(val_acc)
        our_tests.append(test_acc)
        noen_our_vals.append(noen_val_acc)
        noen_our_tests.append(noen_test_acc)

        log_step_perf(step_vals, step_tests, step_noen_vals,
                      step_noen_tests, step_perf_path)
        if use_metric:
            if all_step_new_edge is not None:
                print('all_step_new_edge', all_step_new_edge,
                      all_step_new_edge.shape)
                if all_step_new_edge.nelement() != 0:
                    metric = eval_metric(all_step_new_edge, gold_adj, node_degree,
                                         metric_txt_path, metric_fig_path)
                else:
                    metric = -1
                all_run_metric.append(metric)
            print('all_run_metric', all_run_metric, len(all_run_metric))

    log_run_perf(base_vals, base_tests, our_vals, our_tests,
                 run_perf_path, noen_our_vals, noen_our_tests)
    if use_metric:
        log_run_metric(all_run_metric, test_acc, filename=metric_txt_path)