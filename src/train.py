import sys
import os.path as osp
import os
import random
from tqdm import tqdm
import time
import gc
import argparse

from classes import Net_1, Net_small, LncRNA_Protein_Interaction_dataset

from methods import get_num_of_subgraph, dataset_analysis, average_list, Sensitivity_Precision_Recall_Specificity_MCC

from torch_geometric.data import DataLoader

import torch
import torch.nn.functional as F
from torch.optim import *


def parse_args():
    parser = argparse.ArgumentParser(description="generate_dataset.")
    parser.add_argument('--name', default='RPI369_windowSize=5_0703', help='the name of this object')
    parser.add_argument('--datasetName', default='RPI369', help='raw interactions dataset')
    parser.add_argument('--hopNumber', default=2, help='hop number of subgraph')
    parser.add_argument('--node2vecWindowSize', default=5, help='node2vec window size')
    parser.add_argument('--shuffle', default=True, help='shuffle interactions before generate dataset')
    parser.add_argument('--crossValidation', default=True, help='do cross validation')
    parser.add_argument('--foldNumber', default=5, help='fold number of cross validation')
    parser.add_argument('--epochNumber', default=200, help='number of training epoch')
    parser.add_argument('--initialLearningRate', default=0.005, help='Initial learning rate')
    parser.add_argument('--l2WeightDecay', default=0.0005, help='L2 weight')

    return parser.parse_args()


def train():
    model.train()
    loss_all = 0
    for data in train_loader:
        data = data.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, data.y)
        loss.backward()
        loss_all += data.num_graphs * loss.item()
        optimizer.step()
    return loss_all / len(train_dataset)


if __name__ == "__main__":
    #参数
    args = parse_args()

    if args.shuffle == True:
        dataset_path = f'data/dataset/_{args.datasetName}_{args.hopNumber}_hop_node2vecWindowSize={args.node2vecWindowSize}_shuffled_dataset'
    else:
        dataset_path = f'data/dataset/_{args.datasetName}_{args.hopNumber}_hop_node2vecWindowSize={args.node2vecWindowSize}_notShuffled_dataset'
    # 读取数据集
    dataset = LncRNA_Protein_Interaction_dataset(root=dataset_path)
    
    if args.shuffle == False:
        dataset = dataset.shuffle()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    saving_path = f'result/{args.name}'
    if osp.exists(saving_path):
        raise Exception('已经有同名的训练')
    else:
        os.makedirs(saving_path)

    if args.crossValidation == True:
        # k折交叉验证
        k = args.foldNumber
        step_length = len(dataset) // k
        
        # 迭代次数
        num_of_epoch = args.epochNumber

        # 学习率
        LR = args.initialLearningRate

        # L2正则化系数
        L2_weight_decay = args.l2WeightDecay

        # 准备log
        log_path = saving_path + '/log.txt'
        result_file = open(file=log_path, mode='w')
        result_file.write(f'database：{args.datasetName}\n')
        result_file.write(f'node2vec_windowSize = {args.node2vecWindowSize}\n')
        result_file.write(f'{k}折交叉验证\n')
        result_file.write(f'迭代次数：{num_of_epoch}\n')
        result_file.write(f'学习率：初始{LR}，每当loss增加时就乘0.95\n')
        result_file.write(f'L2正则化，系数{L2_weight_decay}\n')

        # 记录启示时间
        start_time = time.time()
        Sensitivity_list = []
        Precision_list = []
        Recall_list = []
        Specificity_list = []
        MCC_list = []
        for i in range(k):
            print('第{:d}折开始'.format(i+1))
            # 创建保存模型的文件夹
            os.makedirs(saving_path + f'/model_{i}_fold')
            # 创建模型
            num_of_classes = 2
            
            if i != 0:
                del model
            gc.collect()
            model = Net_1(dataset.num_node_features, num_of_classes).to(device)
            
            optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=L2_weight_decay)
            # scheduler = lr_scheduler.MultiStepLR(optimizer,milestones=[int(num_of_epoch * 0.2),int(num_of_epoch * 0.8)],gamma = 0.8)
            scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer=optimizer, gamma=0.95)

            # 训练集和测试集
            test_dataset_start = 0 + i * step_length
            test_dataset_end = (i + 1) * step_length
            test_dataset = dataset[test_dataset_start:test_dataset_end]
            train_dataset = dataset[0:test_dataset_start] + dataset[test_dataset_end:dataset.len()]

            print('训练集数据数量：', len(test_dataset), '测试集数据数量：', len(train_dataset))
            print('训练集')
            dataset_analysis(train_dataset)
            print('测试集')
            dataset_analysis(test_dataset)

            train_loader = DataLoader(train_dataset, batch_size=60)
            test_loader = DataLoader(test_dataset, batch_size=60)

            # 训练开始
            loss_last = float('inf')
            for epoch in range(num_of_epoch):
                loss = train()

                # loss增大时,降低学习率
                if loss > loss_last:
                    scheduler.step()
                loss_last = loss

                # 训练中评价模型，监视训练过程中的模型变化, 并且写入文件
                if (epoch + 1) % 10 == 0 and epoch != num_of_epoch - 1:
                    # 用Sensitivity, Precision, Recall, MCC评价模型
                    # Sensitivity, Precision, Recall ,MCC = Sensitivity_Precision_Recall_MCC(model, train_loader, device)
                    Sensitivity, Precision, Recall, Specificity, MCC = Sensitivity_Precision_Recall_Specificity_MCC(model, train_loader, device)
                    output = 'Epoch: {:03d}, 训练集, Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(epoch + 1, Sensitivity, Precision, Recall, Specificity, MCC)
                    print(output)
                    result_file.write(output + '\n')
                    # Sensitivity, Precision, Recall, MCC = Sensitivity_Precision_Recall_MCC(model, test_loader, device)
                    Sensitivity, Precision, Recall, Specificity, MCC = Sensitivity_Precision_Recall_Specificity_MCC(model, test_loader, device)
                    output = 'Epoch: {:03d}, 测试集, Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(epoch + 1, Sensitivity, Precision, Recall, Specificity, MCC)
                    print(output)
                    result_file.write(output + '\n')
                    # 保存模型
                    network_model_path = saving_path + f'/model_{i}_fold/{epoch+1}'
                    torch.save(model.state_dict(), network_model_path)

            # 训练结束，评价模型，并且把结果写入文件
            Sensitivity, Precision, Recall, Specificity, MCC = Sensitivity_Precision_Recall_Specificity_MCC(model, train_loader, device)
            output = '第{:03d}折结果, 训练集, Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(i + 1, Sensitivity, Precision, Recall, Specificity, MCC)
            print(output)
            result_file.write(output + '\n')
            Sensitivity, Precision, Recall, Specificity, MCC = Sensitivity_Precision_Recall_Specificity_MCC(model, test_loader, device)
            output = '第{:03d}折结果, 测试集, Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(i + 1, Sensitivity, Precision, Recall, Specificity, MCC)
            print(output)

            Sensitivity_list.append(Sensitivity)
            Precision_list.append(Precision)
            Recall_list.append(Recall)
            Specificity_list.append(Specificity)
            MCC_list.append(MCC)

            result_file.write(output + '\n')
            # 把模型存起来
            network_model_path = saving_path + f'/model_{i}_fold/{num_of_epoch}'
            torch.save(model.state_dict(), network_model_path)

        # k折交叉验证完毕
        end_time = time.time()
        print('耗时', end_time - start_time)
        result_file.write('耗时' + str(end_time - start_time) + '\n')
        

        # 计算平均的Sensitivity, Precision, Recall, MCC
        Sensitivity_average = average_list(Sensitivity_list)
        Precision_average = average_list(Precision_list)
        Recall_average = average_list(Recall_list)
        Specificity_average = average_list(Specificity_list)
        MCC_average = average_list(MCC_list)

        # 输出最终的结果
        print('最终结果，Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(Sensitivity_average, Precision_average, Recall_average, Specificity_average, MCC_average))
        result_file.write('最终结果，Sensitivity: {:.5f}, Precision: {:.5f}, Recall: {:.5f}, Specificity: {:.5f}, MCC: {:.5f}'.format(Sensitivity_average, Precision_average, Recall_average, Specificity_average, MCC_average))

        result_file.close()
        
        print('\nexit\n')