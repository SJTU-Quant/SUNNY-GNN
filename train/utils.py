import os
import torch
import dgl
from tqdm import tqdm
from models import snexgnn, hgn, gat, gcn


def edge_hop_mask(sg, target_ntype=None, k=2):
    is_homogeneous = sg.is_homogeneous
    if not is_homogeneous:
        edge_types = sg.etypes
        node_types = sg.ntypes
        sg = dgl.to_homogeneous(sg)
        src_target = torch.nonzero(sg.ndata['_TYPE']==node_types.index(target_ntype))[0].item()
    else:
        src_target = 0
    e_h_mask = torch.tensor([], dtype=torch.bool)
    src = [[src_target]]
    for i in range(k):
        one_hop_sampler = dgl.dataloading.MultiLayerFullNeighborSampler(1)
        one_hop_loader = dgl.dataloading.DataLoader(sg, src[i],
                                                   one_hop_sampler, batch_size=1, shuffle=False)
        neighbors = []
        h_mask = torch.zeros(sg.number_of_edges(), dtype=torch.bool)
        for j, (ng, _, _) in enumerate(one_hop_loader):
            ng_lst = ng.numpy().tolist()
            neighbors.extend(ng_lst)
            edge_ids = sg.edge_ids(ng, [src[i][j]]*len(ng))
            h_mask[edge_ids] = 1
        src.append(list(set(neighbors)))
        e_h_mask = torch.cat((e_h_mask, h_mask.unsqueeze(0)), dim=0)

    if not is_homogeneous:
        e_h_mask_dict = {}
        for i in range(len(edge_types)):
            etype = edge_types[i]
            a = torch.nonzero(sg.edata[dgl.ETYPE] == i).view(-1)
            e_h_mask_dict[etype] = e_h_mask[:, a].T
        return e_h_mask_dict

    return e_h_mask.T


def accuracy(y_pred, y_true):
    y_true = y_true.squeeze().long()
    preds = y_pred.max(1)[1].type_as(y_true)
    correct = preds.eq(y_true).double()
    correct = correct.sum().item()
    return correct / len(y_true)


def get_model(cfg):
    graph_path = cfg.graph_path
    index_path = cfg.index_path
    method = cfg.method
    data_hyparams = cfg.hyparams['data']

    dataset = cfg.dataset
    ckpt_dir = cfg.ckpt_dir
    encoder_type = cfg.encoder_type
    num_classes = data_hyparams['num_classes']
    target_ntype = data_hyparams['target_ntype']

    n_layer = 2

    gs, _ = dgl.load_graphs(graph_path)
    g = gs[0]
    if g.is_homogeneous:
        g = dgl.add_self_loop(g)
    in_dim = {n: g.nodes[n].data['nfeat'].shape[1] for n in g.ntypes}
    info = torch.load(index_path)

    if method == 'gat':
        model = gat.GAT(in_dim[target_ntype], 256, 64, [8, 1], num_classes)

    elif method == 'gcn':
        model = gcn.GCN(in_dim[target_ntype], 256, 64, num_classes)

    elif method == 'simplehgn':
        edge_type_num = len(g.etypes)
        model = hgn.SimpleHeteroHGN(32, edge_type_num, in_dim, 32, num_classes, n_layer,
                                        [8] * n_layer, 0.5, 0.5, 0.05, True, 0.05, True)
    elif method == 'snexgnn':
        method_cfg = cfg.hyparams[method][cfg.encoder_type]
        if encoder_type == 'gat':
            pret_encoder = gat.GAT(in_dim[target_ntype], 256, 64, [8, 1], num_classes)
            encoder = gat.GAT(in_dim[target_ntype], 256, 64, [8, 1], num_classes)
        elif encoder_type == 'gcn':
            pret_encoder = gcn.GCN(in_dim[target_ntype], 256, 64, num_classes)
            encoder = gcn.GCN(in_dim[target_ntype], 256, 64, num_classes)

        pret_encoder.load_state_dict(torch.load(f'{ckpt_dir}/{dataset}/{encoder_type}-seed-{cfg.seed}-pretrain.pt'))
        for param in pret_encoder.parameters():
            param.requires_grad = False

        if cfg.eval_explanation:
            encoder.load_state_dict(torch.load(f'{ckpt_dir}/{dataset}/{encoder_type}-seed-{cfg.seed}-pretrain.pt'))
            for param in encoder.parameters():
                param.requires_grad = False

        extractor = snexgnn.ExtractorMLP(96, False)
        model = snexgnn.SNexGNN(pret_encoder, encoder, extractor, in_dim[target_ntype], target_ntype,
                             dropout=method_cfg['dropout'])

    elif method == 'snexhgn':
        method_cfg = cfg.hyparams[method][cfg.encoder_type]
        edge_type_num = len(g.etypes)
        if encoder_type == 'simplehgn':
            n_heads = 8
            pret_encoder = hgn.SimpleHeteroHGN(32, edge_type_num, in_dim, 32, num_classes, n_layer,
                                          [n_heads] * n_layer, 0.5, 0.5, 0.05, True, 0.05, True)
            encoder = hgn.SimpleHeteroHGN(32, edge_type_num, in_dim, 32, num_classes, n_layer,
                                          [n_heads] * n_layer, 0.5, 0.5, 0.05, True, 0.05, True)
            out_heads = 8

        pret_encoder.load_state_dict(torch.load(f'{ckpt_dir}/{dataset}/{encoder_type}-seed-{cfg.seed}-pretrain.pt'))
        for param in pret_encoder.parameters():
            param.requires_grad = False

        extractor = snexgnn.ExtractorMLP(96, False)
        model = snexgnn.SNexHGN(pret_encoder, encoder, extractor, in_dim,
                                target_ntype, n_heads=out_heads, dropout=method_cfg['dropout'])
    else:
        raise NotImplementedError

    if method in ['snexgnn', 'snexhgn']:
        model.set_config(cfg.hyparams[method][cfg.encoder_type])

    return g, model, info


def construct_dataset(g, info, cfg):
    target_ntype = cfg.hyparams['data']['target_ntype']
    if cfg.index is not None:
        train_node = info["train_index"].long()[: cfg.index]
    else:
        train_node = info["train_index"].long()
    valid_node = info["valid_index"].long()
    test_node = info["test_index"].long()
    labels = info['label'].type(torch.int64)
    nodes = torch.arange(g.number_of_nodes(target_ntype))

    dataset = []
    k = 2
    sampler = dgl.dataloading.MultiLayerFullNeighborSampler(k)
    sg_loader = dgl.dataloading.DataLoader(g, {target_ntype: nodes},
                                               sampler, batch_size=1, shuffle=False, drop_last=False)
    print('loading dataset...')
    sg_path = f'{cfg.data_dir}/{cfg.dataset}_sg.bin'
    if os.path.exists(sg_path):
        dataset = dgl.load_graphs(sg_path)[0]
    else:
        i = 0
        for ng, _, _ in tqdm(sg_loader, leave=False):
            sg = dgl.node_subgraph(g, ng)
            sg.edata['e_h_mask'] = edge_hop_mask(sg, target_ntype)
            dataset.append(sg)
            i += 1
        dgl.save_graphs(sg_path, dataset)

    dataset = [[dataset[i], labels[i]] for i in range(len(dataset))]
    print('load dataset done!')
    train_set = torch.utils.data.Subset(dataset, train_node)
    valid_set = torch.utils.data.Subset(dataset, valid_node)
    test_set = torch.utils.data.Subset(dataset, test_node)
    return train_set, valid_set, test_set, dataset
