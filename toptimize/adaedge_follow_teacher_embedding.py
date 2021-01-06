import os.path as osp
import argparse

import torch
import torch.nn.functional as F
from torch_geometric.datasets import Planetoid
import torch_geometric.transforms as T
from torch_geometric.nn import GCNConv, TOP  # noqa
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from torch_geometric.utils import to_dense_adj
import matplotlib.pyplot as plt

import random
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--use_gdc', action='store_true',
                    help='Use GDC preprocessing.')
args = parser.parse_args()

dataset = 'Cora'
path = osp.join(osp.dirname(osp.realpath(__file__)), '..', 'data', dataset)
dataset = Planetoid(path, dataset, transform=T.NormalizeFeatures())
data = dataset[0]

print()
print(f'Dataset: {dataset}:')
print('===========================================================================================================')
print(f'Number of graphs: {len(dataset)}')
print(f'Number of features: {dataset.num_features}')
print(f'Number of classes: {dataset.num_classes}')

print()
print(data)
print('===========================================================================================================')

# Gather some statistics about the graph.
print(f'Number of nodes: {data.num_nodes}')
print(f'Number of edges: {data.num_edges}')
print(f'Average node degree: {data.num_edges / data.num_nodes:.2f}')
print(f'Number of training nodes: {data.train_mask.sum()}')
print(f'Training node label rate: {int(data.train_mask.sum()) / data.num_nodes:.2f}')
print(f'Contains isolated nodes: {data.contains_isolated_nodes()}')
print(f'Contains self-loops: {data.contains_self_loops()}')
print(f'Is undirected: {data.is_undirected()}')

gold_Y = F.one_hot(data.y).float()
gold_A = torch.matmul(gold_Y, gold_Y.T)

print()
print('Label Relation')
print('============================================================')
print(f'Gold Label Y: {gold_Y}')
print(f'Shape: {gold_Y.shape}')
print(f'Transpose of Y: {gold_Y.T}')
print(f'Shape: {gold_Y.T.shape}')
print(f'Gold A: {gold_A}')
print(f'Shape: {gold_A.shape}')

def compare_topology(pred_A, gold_A, cm_filename='confusion_matrix_display'):
    flat_pred_A = pred_A.detach().cpu().view(-1)
    flat_gold_A = gold_A.detach().cpu().view(-1)
    conf_mat = confusion_matrix(y_true=flat_gold_A, y_pred=flat_pred_A)
    print('conf_mat', conf_mat, conf_mat.shape)
    print('conf_mat.ravel()', conf_mat.ravel(), conf_mat.ravel().shape)
    tn, fp, fn, tp = conf_mat.ravel()
    ppv = tp/(tp+fp)
    npv = tn/(tn+fn)
    tpr = tp/(tp+fn)
    tnr = tn/(tn+fp)
    f1 = 2*(ppv*tpr)/(ppv+tpr)
    print()
    print('Confusion Matrix')
    print('============================================================')
    print(f'Flatten A: {flat_pred_A}')
    print(f'Shape: {flat_pred_A.shape}')
    print(f'Number of Positive Prediction: {flat_pred_A.sum()} ({flat_pred_A.sum().true_divide(len(flat_pred_A))})')
    print(f'Flatten Gold A: {flat_gold_A}')
    print(f'Shape: {flat_gold_A.shape}')
    print(f'Number of Positive Class: {flat_gold_A.sum()} ({flat_gold_A.sum().true_divide(len(flat_gold_A))})')
    print(f'Confusion matrix: {conf_mat}')
    print(f'Raveled Confusion Matrix: {conf_mat.ravel()}')
    print(f'True positive: {tp} # 1 -> 1')
    print(f'False positive: {fp} # 0 -> 1')
    print(f'True negative: {tn} # 0 -> 0')
    print(f'False negative: {fn} # 1 -> 0')
    print(f'Precision: {round(ppv,2)} # TP/(TP+FP)')
    print(f'Negative predictive value: {round(npv,2)} # TN/(TN+FN)')
    print(f'Recall: {round(tpr,2)} # TP/P')
    print(f'Selectivity: {round(tnr,2)} # TN/N')
    print(f'F1 score: {f1}')

    disp = ConfusionMatrixDisplay(confusion_matrix=conf_mat, display_labels=[0,1])
    disp.plot(values_format='d')
    plt.savefig(cm_filename+'.png')


if args.use_gdc:
    gdc = T.GDC(self_loop_weight=1, normalization_in='sym',
                normalization_out='col',
                diffusion_kwargs=dict(method='ppr', alpha=0.05),
                sparsification_kwargs=dict(method='topk', k=128,
                                           dim=0), exact=True)
    data = gdc(data)




seed = 0
run = 0
class Net(torch.nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = GCNConv(dataset.num_features, 16, cached=True,
                             normalize=not args.use_gdc)
        self.conv2 = GCNConv(16, dataset.num_classes, cached=True,
                             normalize=not args.use_gdc)

    def forward(self):
        x, edge_index, edge_weight = data.x, data.edge_index, data.edge_attr
        x = F.relu(self.conv1(x, edge_index, edge_weight))
        x = F.dropout(x, training=self.training)
        final = self.conv2(x, edge_index, edge_weight)
        return final, F.log_softmax(final, dim=1)

random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
np.random.seed(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model, data = Net().to(device), data.to(device)
optimizer = torch.optim.Adam([
    dict(params=model.conv1.parameters(), weight_decay=5e-4),
    dict(params=model.conv2.parameters(), weight_decay=0)
], lr=0.01)  # Only perform weight-decay on first convolution.

print()
print('Model', model)
print('Optimizer', optimizer)

def train():
    print()
    model.train()
    optimizer.zero_grad()
    final, logits = model()

    task_loss = F.nll_loss(logits[data.train_mask], data.y[data.train_mask])
    # print('Task loss', task_loss)

    total_loss = task_loss

    total_loss.backward()
    optimizer.step()

@torch.no_grad()
def test():
    model.eval()
    (final, logits), accs = model(), []
    for _, mask in data('train_mask', 'val_mask', 'test_mask'):
        pred = logits[mask].max(1)[1]
        acc = pred.eq(data.y[mask]).sum().item() / mask.sum().item()
        accs.append(acc)
    return accs

@torch.no_grad()
def final_and_yyt_for_supervision():
    model.eval()
    final, logits = model()
    pred = logits.max(1)[1]
    Y = F.one_hot(pred).float()
    YYT = torch.matmul(Y, Y.T)
    return final, YYT

print("Start Training", run)
print('===========================================================================================================')
best_val_acc = test_acc = 0
for epoch in range(1, 201):
    train()
    train_acc, val_acc, tmp_test_acc = test()
    if val_acc > best_val_acc:
        best_val_acc = val_acc
        test_acc = tmp_test_acc
    log = 'Epoch: {:03d}, Train: {:.4f}, Val: {:.4f}, Test: {:.4f}'
    print(log.format(epoch, train_acc, best_val_acc, test_acc))
    # input()
print('Run', run, 'Val. Acc.', best_val_acc, 'Test Acc.', test_acc)

print("Finished Training", run, '\n')

input('Confusion Matrix '+str(run))
prev_final, YYT = final_and_yyt_for_supervision()

A = to_dense_adj(data.edge_index)[0]
A.fill_diagonal_(1)
print('A', A, A.shape)
# print('ok?', torch.all(A==1 or A==0))
compare_topology(A, gold_A, cm_filename='main'+str(run))










val_accs, test_accs = [], []

for run in range(1, 5 + 1):

    input("\nStart Training "+str(run)) 

    class Net(torch.nn.Module):
        def __init__(self, x, edge_index, edge_weight):
            super(Net, self).__init__()
            self.top1 = TOP()
            self.conv1 = GCNConv(dataset.num_features, 16, cached=True,
                                normalize=not args.use_gdc)
            self.top2 = TOP()
            self.conv2 = GCNConv(16, dataset.num_classes, cached=True,
                                normalize=not args.use_gdc)
            self.x = x
            self.edge_index = edge_index
            self.edge_weight = edge_weight

        def forward(self):
            x, edge_index, edge_weight = self.x, self.edge_index, self.edge_weight
            edge_index, edge_weight = self.top1(x, edge_index, edge_weight)
            x = F.relu(self.conv1(x, edge_index, edge_weight))
            x = F.dropout(x, training=self.training)
            edge_index, edge_weight = self.top2(x, edge_index, edge_weight)
            self.edge_index, self.edge_weight = edge_index, edge_weight
            final = self.conv2(x, edge_index, edge_weight)
            return final, F.log_softmax(x, dim=1)

    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model, data = Net(data.x, data.edge_index, data.edge_attr).to(device), data.to(device)
    optimizer = torch.optim.Adam([
        dict(params=model.top1.parameters(), weight_decay=0),
        dict(params=model.conv1.parameters(), weight_decay=5e-4),
        dict(params=model.top2.parameters(), weight_decay=0),
        dict(params=model.conv2.parameters(), weight_decay=0)
    ], lr=0.01)  # Only perform weight-decay on first convolution.

    print()
    print('Model', model)
    print('Optimizer', optimizer)

    def train():
        print()
        model.train()
        optimizer.zero_grad()
        final, logits = model()

        task_loss = F.nll_loss(logits[data.train_mask], data.y[data.train_mask])
        # print('Task loss', task_loss)

        # link_loss = TOP.get_link_prediction_loss(model)
        # print('Link loss', link_loss)
        
        redundancy_loss = F.mse_loss(final, prev_final, reduction = 'mean')
        # print('Redundancy loss', redundancy_loss)

        total_loss = task_loss + 1 * redundancy_loss
        # print('Total loss', total_loss, '\n')

        total_loss.backward()
        optimizer.step()

    @torch.no_grad()
    def test():
        model.eval()
        (final, logits), accs = model(), []
        for _, mask in data('train_mask', 'val_mask', 'test_mask'):
            pred = logits[mask].max(1)[1]
            acc = pred.eq(data.y[mask]).sum().item() / mask.sum().item()
            accs.append(acc)
        return accs

    @torch.no_grad()
    def final_and_yyt_for_supervision():
        model.eval()
        final, logits = model()
        pred = logits.max(1)[1]
        Y = F.one_hot(pred).float()
        YYT = torch.matmul(Y, Y.T)
        return final, YYT
    
    print('===========================================================================================================')
    best_val_acc = test_acc = 0
    for epoch in range(1, 601):
        train()
        train_acc, val_acc, tmp_test_acc = test()
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            test_acc = tmp_test_acc
        log = 'Epoch: {:03d}, Train: {:.4f}, Val: {:.4f}, Test: {:.4f}'
        print(log.format(epoch, train_acc, best_val_acc, test_acc))
    print('Run', run, 'Val. Acc.', best_val_acc, 'Test Acc.', test_acc)

    val_accs.append(best_val_acc)
    test_accs.append(test_acc)

    print("Finished Training", run, '\n')

    input('Confusion matrix ' + str(run))
    # prev_final, YYT = final_and_yyt_for_supervision()
    A = to_dense_adj(model.edge_index)[0]
    A.fill_diagonal_(1)
    A[A>1] = 1
    print('A', A, A.shape)
    # print('ok?', torch.all(A==1 or A==0))
    compare_topology(A, gold_A, cm_filename='main'+str(run))

# Analytics
print('Task Loss + Link Prediction Loss')
print('Dataset split is the public fixed split')

val_accs = np.array(val_accs)
mean = np.mean(val_accs)
std = np.std(val_accs)

print('Val. Acc.:', mean, '+/-', str(std))

test_accs = np.array(test_accs)
mean = np.mean(test_accs)
std = np.std(test_accs)

print('Test. Acc.:', mean, '+/-', str(std))