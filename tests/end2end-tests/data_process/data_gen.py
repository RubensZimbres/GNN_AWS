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

    Generate example graph data using built-in datasets for node classifcation,
    node regression, edge classification and edge regression.
"""
import copy
import json
import os
import pyarrow.parquet as pq
import pyarrow as pa
import numpy as np

def write_data_parquet(data, data_file):
    """ Write data to a parquet file.
    """
    df = {}
    for key in data:
        arr = data[key]
        assert len(arr.shape) == 1 or len(arr.shape) == 2
        if len(arr.shape) == 1:
            df[key] = arr
        else:
            df[key] = [arr[i] for i in range(len(arr))]
    table = pa.Table.from_arrays(list(df.values()), names=list(df.keys()))
    pq.write_table(table, data_file)

node_id1 = np.unique(np.random.randint(0, 1000000000, 10000))
node_text = np.array([str(nid) for nid in node_id1])
node_data1 = {
    'id': node_id1,
    'data': node_id1,
    'text': node_text,
    'label': node_id1 % 100,
}

node_id2 = np.arange(20000)
node_data2 = {
    'id': node_id2,
    'data': np.repeat(node_id2, 5).reshape(len(node_id2), 5),
}

node_id3 = np.unique(np.random.randint(0, 1000000000, 5000))
node_id3_str = np.array([str(nid) for nid in node_id3])
node_data3 = {
    'id': node_id3_str,
}

src1 = node_data1['id'][np.random.randint(0, 10000, 100000)]
dst1 = node_data2['id'][np.random.randint(0, 20000, 100000)]
edge_data1 = {
    'src': src1,
    'dst': dst1,
    'label': (src1 + dst1) % 100,
}
edge_data2 = {
    'src': node_data1['id'][np.random.randint(0, 10000, 50000)],
    'dst': node_data1['id'][np.random.randint(0, 10000, 50000)],
}

src3 = node_data2['id'][np.random.randint(0, 20000, 100000)]
dst_idx = np.random.randint(0, 5000, 100000)
edge_data3 = {
    'src': src3,
    'dst': node_data3['id'][dst_idx],
    'data': src3 + node_id3[dst_idx],
}

in_dir = '/tmp/test_data/'
out_dir = '/tmp/test_out/'

os.makedirs(in_dir, exist_ok=True)
os.makedirs(out_dir, exist_ok=True)

def split_data(data, num):
    new_data_list = [{} for _ in range(num)]
    for key, val in data.items():
        for i, val in enumerate(np.split(val, num)):
            new_data_list[i][key] = val
    return new_data_list

for i, node_data in enumerate(split_data(node_data1, 5)):
    write_data_parquet(node_data, os.path.join(in_dir, f'node_data1_{i}.parquet'))
for i, node_data in enumerate(split_data(node_data2, 10)):
    write_data_parquet(node_data, os.path.join(in_dir, f'node_data2_{i}.parquet'))
for i, node_data in enumerate(split_data(node_data3, 10)):
    write_data_parquet(node_data, os.path.join(in_dir, f'node_data3_{i}.parquet'))
for i, edge_data in enumerate(split_data(edge_data1, 10)):
    write_data_parquet(edge_data, os.path.join(in_dir, f'edge_data1_{i}.parquet'))
for i, edge_data in enumerate(split_data(edge_data2, 10)):
    write_data_parquet(edge_data, os.path.join(in_dir, f'edge_data2_{i}.parquet'))
for i, edge_data in enumerate(split_data(edge_data3, 10)):
    write_data_parquet(edge_data, os.path.join(in_dir, f'edge_data3_{i}.parquet'))

node_conf = [
    {
        "node_id_col": "id",
        "node_type": "node1",
        "format": {"name": "parquet"},
        "files": os.path.join(in_dir, "node_data1_*.parquet"),
        "features": [
            {
                "feature_col": "data",
                "feature_name": "feat",
            },
            {
                "feature_col": "text",
                # tokenize_hf generates multiple features.
                # It defines feature names itself.
                "transform": {"name": "tokenize_hf",
                              "bert_model": "bert-base-uncased",
                              "max_seq_length": 16},
            },
        ],
        "labels":       [
            {
                "label_col":    "label",
                "task_type":    "classification",
                "split_type":   [0.8, 0.2, 0.0],
            },
        ],
    },
    {
        "node_id_col": "id",
        "node_type": "node2",
        "format": {"name": "parquet"},
        "files": os.path.join(in_dir, "node_data2_*.parquet"),
        "features": [
            {
                "feature_col": "data",
                "feature_name": "feat",
            },
        ],
    },
    {
        "node_id_col": "id",
        "node_type": "node3",
        "format": {"name": "parquet"},
        "files": os.path.join(in_dir, "node_data3_*.parquet"),
    },
]
edge_conf = [
    {
        "source_id_col":    "src",
        "dest_id_col":      "dst",
        "relation":         ("node1", "relation1", "node2"),
        "format":           {"name": "parquet"},
        "files":            os.path.join(in_dir, "edge_data1_*.parquet"),
        "labels":       [
            {
                "label_col":    "label",
                "task_type":    "classification",
                "split_type":   [0.8, 0.2, 0.0],
            },
        ],
    },
    {
        "source_id_col":    "src",
        "dest_id_col":      "dst",
        "relation":         ("node1", "relation2", "node1"),
        "format":           {"name": "parquet"},
        "files":            os.path.join(in_dir, "edge_data2_*.parquet"),
    },
    {
        "source_id_col":    "src",
        "dest_id_col":      "dst",
        "relation":         ("node2", "relation3", "node3"),
        "format":           {"name": "parquet"},
        "files":            os.path.join(in_dir, "edge_data3_*.parquet"),
        "features": [
            {
                "feature_col": "data",
                "feature_name": "feat",
            },
        ],
    },
]
transform_conf = {
    "node": node_conf,
    "edge": edge_conf,
}
json.dump(transform_conf, open(os.path.join(in_dir, 'test_data_transform.conf'), 'w'), indent=4)
