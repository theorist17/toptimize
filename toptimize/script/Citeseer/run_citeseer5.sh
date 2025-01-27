# Path
cd /data/brandon/toptimize/toptimize

### GCN ###

## Ours
# python train.py "Citeseer/Ours_DL_paper" -b GCN -d Citeseer -tr 100 -t 7 -l2 0
# python train.py "Citeseer/no_drop_new_trial1" -b GCN -d Citeseer -tr 100 -t 9 -te 200 -et
# python train.py "Citeseer/no_drop_LL_new_trial1" -b GCN -d Citeseer -tr 100 -t 99999999 -te 200 -l1 0
# python train.py "Citeseer/no_drop_DL_new_trial1" -b GCN -d Citeseer -tr 100 -t 9 -te 200 -l2 0


## No LL
# python train.py "Citeseer/no_drop_LL_real" -b GCN -d Citeseer -tr 100 -t 9999999 -l1 0

## No DL
# python train.py "Citeseer/no_drop_DL_real" -b GCN -d Citeseer -tr 100 -t 7 -l2 0

### GAT ###
python train.py "Citeseer/Ours_dropout_yes_LL" -b GAT -d Citeseer -tr 100 -ts 5 -t 9999999999 -l1 0 -l2 10 -hs 8
# python train.py "Citeseer/Ours_dropout_LL" -b GAT -d Citeseer -tr 100 -ts 5 -t 9999999999 -l1 0 -l2 10 -hs 8
# python train.py "Citeseer/no_LL_paper" -b GAT -d Citeseer -tr 100 -t 100000000 -l1 0

## Ours
# python train.py "Citeseer/no_drop_test1" -b GAT -d Citeseer -tr 10 -t 1 -te 300 -ts 10

## No LL

## No DL

### Cold Start ###

# GCN (0.25, 0.50, 0.75)
# python train.py "Coldstart/Citeseer/0.25_real" -b GCN -d Citeseer -tr 50 -t 7 -csr 0.25
# python train.py "Coldstart/Citeseer/0.50_real" -b GCN -d Citeseer -tr 50 -t 7 -csr 0.50
# python train.py "Coldstart/Citeseer/0.75_real" -b GCN -d Citeseer -tr 50 -t 7 -csr 0.75

# # GAT (0.25, 0.50, 0.75)
# python train.py "Coldstart/Citeseer/0.25_trial1" -b GAT -d Citeseer -tr 100 -t 0.2 -csr 0.25 -te 300
# python train.py "Coldstart/Citeseer/0.50_trial1" -b GAT -d Citeseer -tr 100 -t 0.2 -csr 0.50 -te 300
# python train.py "Coldstart/Citeseer/0.75_trial1" -b GAT -d Citeseer -tr 100 -t 0.2 -csr 0.75 -te 300