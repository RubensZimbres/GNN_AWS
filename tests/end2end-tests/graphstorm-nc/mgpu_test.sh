#!/bin/bash

service ssh restart

DGL_HOME=/root/dgl
GS_HOME=$(pwd)
NUM_TRAINERS=4
NUM_INFERs=2
export PYTHONPATH=$GS_HOME/python/
cd $GS_HOME/training_scripts/gsgnn_np
echo "127.0.0.1" > ip_list.txt
cd $GS_HOME/inference_scripts/np_infer
echo "127.0.0.1" > ip_list.txt


error_and_exit () {
	# check exec status of launch.py
	status=$1
	echo $status

	if test $status -ne 0
	then
		exit -1
	fi
}

echo "**************dataset: MovieLens classification, RGCN layer: 1, node feat: fixed HF BERT, BERT nodes: movie, inference: mini-batch save model save emb node"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/training_scripts/gsgnn_np/ --num_trainers $NUM_TRAINERS --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --ip_config ip_list.txt --ssh_port 2222 "python3 gsgnn_np.py --cf ml_nc.yaml --num-gpus $NUM_TRAINERS --part-config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --save-model-path /data/gsgnn_nc_ml/ --topk-model-to-save 1 --save-embed-path /data/gsgnn_nc_ml/emb/ --n-epochs 3" | tee train_log.txt

error_and_exit $?

# check prints
cnt=$(grep "save_embed_path: /data/gsgnn_nc_ml/emb/" train_log.txt | wc -l)
if test $cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have save_embed_path"
    exit -1
fi

cnt=$(grep "save_model_path: /data/gsgnn_nc_ml/" train_log.txt | wc -l)
if test $cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have save_model_path"
    exit -1
fi

bst_cnt=$(grep "Best Test accuracy" train_log.txt | wc -l)
if test $bst_cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Test accuracy"
    exit -1
fi

cnt=$(grep "Test accuracy" train_log.txt | wc -l)
if test $cnt -lt $((1+$bst_cnt))
then
    echo "We use SageMaker task tracker, we should have Test accuracy"
    exit -1
fi

bst_cnt=$(grep "Best Validation accuracy" train_log.txt | wc -l)
if test $bst_cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Validation accuracy"
    exit -1
fi

cnt=$(grep "Validation accuracy" train_log.txt | wc -l)
if test $cnt -lt $((1+$bst_cnt))
then
    echo "We use SageMaker task tracker, we should have Validation accuracy"
    exit -1
fi

cnt=$(grep "Best Iteration" train_log.txt | wc -l)
if test $cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Iteration"
    exit -1
fi

cnt=$(ls -l /data/gsgnn_nc_ml/ | grep epoch | wc -l)
if test $cnt != 1
then
    echo "The number of save models $cnt is not equal to the specified topk 1"
    exit -1
fi

best_epoch=$(grep "successfully save the model to" train_log.txt | tail -1 | tr -d '\n' | tail -c 1)
echo "The best model is saved in epoch $best_epoch"

echo "**************dataset: Movielens, do inference on saved model"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/inference_scripts/np_infer/ --num_trainers $NUM_INFERs --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --ip_config ip_list.txt --ssh_port 2222 "python3 np_infer_gnn.py --cf ml_nc_infer.yaml --mini-batch-infer false --num-gpus $NUM_INFERs --part-config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --save-embed-path /data/gsgnn_nc_ml/infer-emb/ --restore-model-path /data/gsgnn_nc_ml/epoch-$best_epoch/ --save-predict-path /data/gsgnn_nc_ml/prediction/" | tee log.txt

error_and_exit $?

cnt=$(grep "| Test accuracy" log.txt | wc -l)
if test $cnt -ne 1
then
    echo "We do test, should have test accuracy"
    exit -1
fi

bst_cnt=$(grep "Best Test accuracy" log.txt | wc -l)
if test $bst_cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Test accuracy"
    exit -1
fi

bst_cnt=$(grep "Best Validation accuracy" log.txt | wc -l)
if test $bst_cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Validation accuracy"
    exit -1
fi

cnt=$(grep "Validation accuracy" log.txt | wc -l)
if test $cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Validation accuracy"
    exit -1
fi

cnt=$(grep "Best Iteration" log.txt | wc -l)
if test $cnt -lt 1
then
    echo "We use SageMaker task tracker, we should have Best Iteration"
    exit -1
fi

python3 $GS_HOME/tests/end2end-tests/check_infer.py --train_embout /data/gsgnn_nc_ml/emb/ --infer_embout /data/gsgnn_nc_ml/infer-emb/

error_and_exit $?

echo "**************dataset: Movielens, do inference on saved model, decoder: dot with a single process"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/inference_scripts/np_infer/ --num_trainers 1 --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --ip_config ip_list.txt --ssh_port 2222 "python3 np_infer_gnn.py --cf ml_nc_infer.yaml --mini-batch-infer false --num-gpus 1 --part-config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --save-embed-path /data/gsgnn_nc_ml/infer-emb-1p/ --restore-model-path /data/gsgnn_nc_ml/epoch-$best_epoch/ --save-predict-path /data/gsgnn_nc_ml/prediction-1p/" | tee log.txt

python3 $GS_HOME/tests/end2end-tests/check_infer.py --train_embout /data/gsgnn_nc_ml/emb/ --infer_embout /data/gsgnn_nc_ml/infer-emb-1p/

error_and_exit $?

echo "**************dataset: MovieLens classification, RGCN layer: 1, node feat: fixed HF BERT, BERT nodes: movie, inference: mini-batch save model save emb node, early stop"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/training_scripts/gsgnn_np/ --num_trainers $NUM_TRAINERS --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --ip_config ip_list.txt --ssh_port 2222 "python3 gsgnn_np.py --cf ml_nc.yaml --num-gpus $NUM_TRAINERS --part-config /data/movielen_100k_train_val_1p_4t/movie-lens-100k.json --save-model-path /data/gsgnn_nc_ml/ --topk-model-to-save 3 --save-embed-path /data/gsgnn_nc_ml/emb/ --enable-early-stop True --call-to-consider-early-stop 2 -e 20 --window-for-early-stop 3 --early-stop-strategy consecutive_increase" | tee exec.log

error_and_exit $?

# check early stop
cnt=$(cat exec.log | grep "Evaluation step" | wc -l)
if test $cnt -eq 20
then
	echo "Early stop should work, but it didn't"
	exit -1
fi

if test $cnt -le 4
then
	echo "Need at least 5 iters"
	exit -1
fi

cnt=$(ls -l /data/gsgnn_nc_ml/ | grep epoch | wc -l)
if test $cnt != 3
then
    echo "The number of save models $cnt is not equal to the specified topk 3"
    exit -1
fi

rm -fr /data/gsgnn_nc_ml/*

echo "**************dataset: MovieLens classification, RGCN layer: 1, node feat: BERT nodes: movie, user inference: mini-batch save model save emb node"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/training_scripts/gsgnn_np/ --num_trainers $NUM_TRAINERS --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --ip_config ip_list.txt --ssh_port 2222 "python3 gsgnn_np.py --cf ml_nc_utext.yaml --num-gpus $NUM_TRAINERS --part-config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --save-model-path /data/gsgnn_nc_ml_text/ --topk-model-to-save 1 --save-embed-path /data/gsgnn_nc_ml_text/emb/ --n-epochs 3" | tee train_log.txt

error_and_exit $?

cnt=$(ls -l /data/gsgnn_nc_ml_text/ | grep epoch | wc -l)
if test $cnt != 1
then
    echo "The number of save models $cnt is not equal to the specified topk 1"
    exit -1
fi

best_epoch=$(grep "successfully save the model to" train_log.txt | tail -1 | tr -d '\n' | tail -c 1)
echo "The best model is saved in epoch $best_epoch"

echo "**************dataset: Movielens, do inference on saved model, decoder: dot"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/inference_scripts/np_infer/ --num_trainers $NUM_INFERs --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --ip_config ip_list.txt --ssh_port 2222 "python3 np_infer_gnn.py --cf ml_nc_text_infer.yaml --mini-batch-infer false --num-gpus $NUM_INFERs --part-config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --save-embed-path /data/gsgnn_nc_ml_text/infer-emb/ --restore-model-path /data/gsgnn_nc_ml_text/epoch-$best_epoch/ --save-predict-path /data/gsgnn_nc_ml_text/prediction/" | tee log.txt

error_and_exit $?

cnt=$(grep "| Test accuracy" log.txt | wc -l)
if test $cnt -ne 1
then
    echo "We do test, should have test accuracy"
    exit -1
fi

python3 $GS_HOME/tests/end2end-tests/check_infer.py --train_embout /data/gsgnn_nc_ml_text/emb/ --infer_embout /data/gsgnn_nc_ml_text/infer-emb/

error_and_exit $?

echo "**************dataset: MovieLens classification, RGCN layer: 1, node feat: BERT nodes: movie, user inference: mini-batch save model save emb node, train_nodes 0"
python3 $DGL_HOME/tools/launch.py --workspace $GS_HOME/training_scripts/gsgnn_np/ --num_trainers $NUM_TRAINERS --num_servers 1 --num_samplers 0 --part_config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --ip_config ip_list.txt --ssh_port 2222 "python3 gsgnn_np.py --cf ml_nc_utext.yaml --num-gpus $NUM_TRAINERS --part-config /data/movielen_100k_text_train_val_1p_4t/movie-lens-100k-text.json --save-model-path /data/gsgnn_nc_ml_text/ --topk-model-to-save 1 --save-embed-path /data/gsgnn_nc_ml_text/emb/ --n-epochs 3 --lm-train-nodes 0" | tee train_log.txt

rm -fr /data/gsgnn_nc_ml_text/*
