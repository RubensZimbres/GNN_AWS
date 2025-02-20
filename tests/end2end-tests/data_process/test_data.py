"""
    Copyright 2023 Contributors

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
import os
import json
import dgl
import pyarrow.parquet as pq
import pyarrow as pa
import numpy as np
import torch as th
import argparse

def read_data_parquet(data_file):
    table = pq.read_table(data_file)
    pd = table.to_pandas()
    return {key: np.array(pd[key]) for key in pd}

argparser = argparse.ArgumentParser("Preprocess graphs")
argparser.add_argument("--graph_format", type=str, required=True,
                       help="The constructed graph format.")
argparser.add_argument("--graph_dir", type=str, required=True,
                       help="The path of the constructed graph.")
argparser.add_argument("--conf_file", type=str, required=True,
                       help="The configuration file.")
args = argparser.parse_args()
out_dir = args.graph_dir
conf_file = args.conf_file

if args.graph_format == "DGL":
    g = dgl.load_graphs(os.path.join(out_dir, "test.dgl"))[0][0]
elif args.graph_format == "DistDGL":
    from dgl.distributed.graph_partition_book import _etype_str_to_tuple
    g, node_feats, edge_feats, gpb, graph_name, ntypes_list, etypes_list = \
            dgl.distributed.load_partition(os.path.join(out_dir, 'test.json'), 0)
    g = dgl.to_heterogeneous(g, ntypes_list, [etype[1] for etype in etypes_list])
    for key, val in node_feats.items():
        ntype, name = key.split('/')
        g.nodes[ntype].data[name] = val
    for key, val in edge_feats.items():
        etype, name = key.split('/')
        etype = _etype_str_to_tuple(etype)
        g.edges[etype].data[name] = val
else:
    raise ValueError('Invalid graph format: {}'.format(args.graph_format))
    
node1_map = read_data_parquet(os.path.join(out_dir, "node1_id_remap.parquet"))
reverse_node1_map = {val: key for key, val in zip(node1_map['orig'], node1_map['new'])}
node3_map = read_data_parquet(os.path.join(out_dir, "node3_id_remap.parquet"))
reverse_node3_map = {val: key for key, val in zip(node3_map['orig'], node3_map['new'])}

# Test the first node data
data = g.nodes['node1'].data['feat'].numpy()
label = g.nodes['node1'].data['label'].numpy()
assert label.dtype == np.int32
orig_ids = np.array([reverse_node1_map[new_id] for new_id in range(g.number_of_nodes('node1'))])
assert np.all(data == orig_ids)
assert np.all(label == orig_ids % 100)
assert th.sum(g.nodes['node1'].data['train_mask']) == int(g.number_of_nodes('node1') * 0.8)
assert th.sum(g.nodes['node1'].data['val_mask']) == int(g.number_of_nodes('node1') * 0.2)
assert th.sum(g.nodes['node1'].data['test_mask']) == 0

# Test the second node data
data = g.nodes['node2'].data['feat'].numpy()
orig_ids = np.arange(g.number_of_nodes('node2'))
assert data.shape[1] == 5
for i in range(data.shape[1]):
    assert np.all(data[:,i] == orig_ids)

# Test the edge data of edge type 1
src_ids, dst_ids = g.edges(etype=('node1', 'relation1', 'node2'))
label = g.edges[('node1', 'relation1', 'node2')].data['label'].numpy()
assert label.dtype == np.int32
src_ids = np.array([reverse_node1_map[src_id] for src_id in src_ids.numpy()])
dst_ids = dst_ids.numpy()
assert np.all((src_ids + dst_ids) % 100 == label)
assert th.sum(g.edges[('node1', 'relation1', 'node2')].data['train_mask']) \
        == int(g.number_of_edges(('node1', 'relation1', 'node2')) * 0.8)
assert th.sum(g.edges[('node1', 'relation1', 'node2')].data['val_mask']) \
        == int(g.number_of_edges(('node1', 'relation1', 'node2')) * 0.2)
assert th.sum(g.edges[('node1', 'relation1', 'node2')].data['test_mask']) == 0

# Test the edge data of edge type 3
src_ids, dst_ids = g.edges(etype=('node2', 'relation3', 'node3'))
feat = g.edges[('node2', 'relation3', 'node3')].data['feat'].numpy()
src_ids = src_ids.numpy()
dst_ids = np.array([int(reverse_node3_map[dst_id]) for dst_id in dst_ids.numpy()])
assert np.all(src_ids + dst_ids == feat)
