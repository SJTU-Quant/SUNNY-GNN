python main.py --method gat --dataset citeseer
python main.py --method gat --dataset cora
python main.py --method gat --dataset pubmed
python main.py --method gat --dataset amazon-photo
python main.py --method gat --dataset coauthor-cs
python main.py --method gat --dataset coauthor-physics

python main.py --method gcn --dataset citeseer
python main.py --method gcn --dataset cora
python main.py --method gcn --dataset pubmed
python main.py --method gcn --dataset amazon-photo
python main.py --method gcn --dataset coauthor-cs
python main.py --method gcn --dataset coauthor-physics

python main.py --method sunny-gnn --encoder gat --dataset citeseer
python main.py --method sunny-gnn --encoder gat --dataset cora
python main.py --method sunny-gnn --encoder gat --dataset pubmed
python main.py --method sunny-gnn --encoder gat --dataset amazon-photo
python main.py --method sunny-gnn --encoder gat --dataset coauthor-cs
python main.py --method sunny-gnn --encoder gat --dataset coauthor-physics

python main.py --method sunny-gnn --encoder gcn --dataset citeseer
python main.py --method sunny-gnn --encoder gcn --dataset cora
python main.py --method sunny-gnn --encoder gcn --dataset pubmed
python main.py --method sunny-gnn --encoder gcn --dataset amazon-photo
python main.py --method sunny-gnn --encoder gcn --dataset coauthor-cs
python main.py --method sunny-gnn --encoder gcn --dataset coauthor-physics
