import os.path as osp
import argparse

import torch
import torch.nn.functional as F
from torch_geometric.datasets import Planetoid
import torch_geometric.transforms as T
from torch_geometric.nn import GCNConv  # noqa
from torch_geometric.utils import to_dense_adj
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
import pickle

parser = argparse.ArgumentParser()
parser.add_argument('--use_gdc', action='store_true',
                    help='Use GDC preprocessing.')
args = parser.parse_args()


dataset = 'Cora'
path = osp.join(osp.dirname(osp.realpath(__file__)), '..', 'data', dataset)
dataset = Planetoid(path, dataset, transform=T.NormalizeFeatures())
data = dataset[0]
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
data =  data.to(device)

if args.use_gdc:
    gdc = T.GDC(self_loop_weight=1, normalization_in='sym',
                normalization_out='col',
                diffusion_kwargs=dict(method='ppr', alpha=0.05),
                sparsification_kwargs=dict(method='topk', k=128,
                                           dim=0), exact=True)
    data = gdc(data)

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
        x = self.conv2(x, edge_index, edge_weight)
        return x, F.log_softmax(x, dim=1)

# A = to_dense_adj(data.edge_index)[0]

# edge_index0 = torch.nonzero(A == 1, as_tuple=False)
# A = A.fill_diagonal_(1)

# gold_Y = F.one_hot(data.y).float()
# gold_A = torch.matmul(gold_Y, gold_Y.T)

###################################################################

# A = A.fill_diagonal_(0) # remove self-loop
# edge_index = torch.nonzero(gold_A == 1, as_tuple=False)


# data.edge_index = edge_index.t().contiguous()

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model, data = Net().to(device), data.to(device)
optimizer = torch.optim.Adam([
    dict(params=model.conv1.parameters(), weight_decay=5e-4),
    dict(params=model.conv2.parameters(), weight_decay=0)
], lr=0.01)  # Only perform weight-decay on first convolution.

with open('final_x.pickle', 'rb') as f:
     final_x = pickle.load(f)

def train():
    model.train()
    optimizer.zero_grad()
    a,b = model()
    # print(a, a.shape)
    # print('#######################')
    # print(b, b.shape)
    pred, target = b[data.train_mask], data.y[data.train_mask]
    loss = F.nll_loss(pred, target) + F.mse_loss(a, final_x, reduction = 'sum')
    # F.mse_loss(a, final_x, reduction = 'sum')
    print(loss)
    loss.backward()
    optimizer.step()
    return a, b


@torch.no_grad()
def test():
    model.eval()
    a, logits = model()
    accs = []
    for _, mask in data('train_mask', 'val_mask', 'test_mask'):
        pred = logits[mask].max(1)[1]
        acc = pred.eq(data.y[mask]).sum().item() / mask.sum().item()
        accs.append(acc)
    return accs

best_val_acc = test_acc = 0
for epoch in range(1, 201):
    train()
    train_acc, val_acc, tmp_test_acc = test()
    # if epoch == 200:
    #     a, b = train()
    #     with open('final_x.pickle', 'wb') as f:
    #         pickle.dump(a, f)
    #     with open('logit.pickle', 'wb') as f:
    #         pickle.dump(b, f)

    if val_acc > best_val_acc:
        best_val_acc = val_acc
        test_acc = tmp_test_acc
    log = 'Epoch: {:03d}, Train: {:.4f}, Val: {:.4f}, Test: {:.4f}'
    print(log.format(epoch, train_acc, best_val_acc, test_acc))



