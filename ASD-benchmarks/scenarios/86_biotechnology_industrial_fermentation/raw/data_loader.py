import os
import numpy as np
import pandas as pd
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler
from utils.timefeatures import time_features
from data_provider.m4 import M4Dataset, M4Meta
import warnings
from dtaidistance import dtw
from sklearn.metrics.pairwise import cosine_similarity
from scipy.spatial.distance import euclidean
warnings.filterwarnings('ignore')


def weighted_dtw(x, y, weights):
    """
    实现加权 DTW 的函数。
    :param x: 输入序列 (M, N) 的 numpy 数组。
    :param y: 比较序列 (M, N) 的 numpy 数组。
    :param weights: 每个变量的权重数组 (N,)。
    :return: 最小的加权 DTW 距离。
    """
    M, N = x.shape
    D = np.zeros((M, M)) + np.inf  # 初始化距离矩阵
    D[0, 0] = 0

    for i in range(1, M):
        for j in range(1, M):
            cost = np.sum(weights * (x[i] - y[j])**2)  # 加权欧式距离
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])

    return D[-1, -1]  # 返回最终的加权 DTW 距离



class Dataset_ETT_hour(Dataset):
    def __init__(self, root_path, flag='train', size=None,
                 features='S', data_path='ETTh1.csv',
                 target='OT', scale=True, timeenc=0, freq='h', percent=100,
                 seasonal_patterns=None):
        if size == None:
            self.seq_len = 24 * 4 * 4
            self.label_len = 24 * 4
            self.pred_len = 24 * 4
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        # init
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.percent = percent
        self.features = features
        self.target = target
        self.scale = scale
        self.timeenc = timeenc
        self.freq = freq

        # self.percent = percent
        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

        self.enc_in = self.data_x.shape[-1]
        self.tot_len = len(self.data_x) - self.seq_len - self.pred_len + 1

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path,
                                          self.data_path))

        border1s = [0, 12 * 30 * 24 - self.seq_len, 12 * 30 * 24 + 4 * 30 * 24 - self.seq_len]
        border2s = [12 * 30 * 24, 12 * 30 * 24 + 4 * 30 * 24, 12 * 30 * 24 + 8 * 30 * 24]

        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]

        if self.set_type == 0:
            border2 = (border2 - self.seq_len) * self.percent // 100 + self.seq_len

        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]
        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        if self.scale:
            train_data = df_data[border1s[0]:border2s[0]]
            self.scaler.fit(train_data.values)
            data = self.scaler.transform(df_data.values)
        else:
            data = df_data.values

        df_stamp = df_raw[['date']][border1:border2]
        df_stamp['date'] = pd.to_datetime(df_stamp.date)
        if self.timeenc == 0:
            df_stamp['month'] = df_stamp.date.apply(lambda row: row.month, 1)
            df_stamp['day'] = df_stamp.date.apply(lambda row: row.day, 1)
            df_stamp['weekday'] = df_stamp.date.apply(lambda row: row.weekday(), 1)
            df_stamp['hour'] = df_stamp.date.apply(lambda row: row.hour, 1)
            data_stamp = df_stamp.drop(['date'], 1).values
        elif self.timeenc == 1:
            data_stamp = time_features(pd.to_datetime(df_stamp['date'].values), freq=self.freq)
            data_stamp = data_stamp.transpose(1, 0)

        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        self.data_stamp = data_stamp

    def __getitem__(self, index):
        feat_id = index // self.tot_len
        s_begin = index % self.tot_len

        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len
        seq_x = self.data_x[s_begin:s_end, feat_id:feat_id + 1]
        seq_y = self.data_y[r_begin:r_end, feat_id:feat_id + 1]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        seq_y_mark = self.data_stamp[r_begin:r_end]

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return (len(self.data_x) - self.seq_len - self.pred_len + 1) * self.enc_in

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_ETT_minute(Dataset):
    def __init__(self, root_path, flag='train', size=None,
                 features='S', data_path='ETTm1.csv',
                 target='OT', scale=True, timeenc=0, freq='t', percent=100,
                 seasonal_patterns=None):
        if size == None:
            self.seq_len = 24 * 4 * 4
            self.label_len = 24 * 4
            self.pred_len = 24 * 4
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        # init
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.percent = percent
        self.features = features
        self.target = target
        self.scale = scale
        self.timeenc = timeenc
        self.freq = freq

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

        self.enc_in = self.data_x.shape[-1]
        self.tot_len = len(self.data_x) - self.seq_len - self.pred_len + 1

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path,
                                          self.data_path))

        border1s = [0, 12 * 30 * 24 * 4 - self.seq_len, 12 * 30 * 24 * 4 + 4 * 30 * 24 * 4 - self.seq_len]
        border2s = [12 * 30 * 24 * 4, 12 * 30 * 24 * 4 + 4 * 30 * 24 * 4, 12 * 30 * 24 * 4 + 8 * 30 * 24 * 4]

        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]

        if self.set_type == 0:
            border2 = (border2 - self.seq_len) * self.percent // 100 + self.seq_len

        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]
        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        if self.scale:
            train_data = df_data[border1s[0]:border2s[0]]
            self.scaler.fit(train_data.values)
            data = self.scaler.transform(df_data.values)
        else:
            data = df_data.values

        df_stamp = df_raw[['date']][border1:border2]
        df_stamp['date'] = pd.to_datetime(df_stamp.date)
        if self.timeenc == 0:
            df_stamp['month'] = df_stamp.date.apply(lambda row: row.month, 1)
            df_stamp['day'] = df_stamp.date.apply(lambda row: row.day, 1)
            df_stamp['weekday'] = df_stamp.date.apply(lambda row: row.weekday(), 1)
            df_stamp['hour'] = df_stamp.date.apply(lambda row: row.hour, 1)
            df_stamp['minute'] = df_stamp.date.apply(lambda row: row.minute, 1)
            df_stamp['minute'] = df_stamp.minute.map(lambda x: x // 15)
            data_stamp = df_stamp.drop(['date'], 1).values
        elif self.timeenc == 1:
            data_stamp = time_features(pd.to_datetime(df_stamp['date'].values), freq=self.freq)
            data_stamp = data_stamp.transpose(1, 0)

        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        self.data_stamp = data_stamp

    def __getitem__(self, index):
        feat_id = index // self.tot_len
        s_begin = index % self.tot_len

        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len
        seq_x = self.data_x[s_begin:s_end, feat_id:feat_id + 1]
        seq_y = self.data_y[r_begin:r_end, feat_id:feat_id + 1]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        seq_y_mark = self.data_stamp[r_begin:r_end]

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return (len(self.data_x) - self.seq_len - self.pred_len + 1) * self.enc_in

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_Custom(Dataset):
    def __init__(self, root_path, flag='train', size=None,
                 features='S', data_path='ETTh1.csv',
                 target='OT', scale=True, timeenc=0, freq='h', percent=100,
                 seasonal_patterns=None):
        if size == None:
            self.seq_len = 24 * 4 * 4
            self.label_len = 24 * 4
            self.pred_len = 24 * 4
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        # init
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.features = features
        self.target = target
        self.scale = scale
        self.timeenc = timeenc
        self.freq = freq
        self.percent = percent

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

        self.enc_in = self.data_x.shape[-1]
        self.tot_len = len(self.data_x) - self.seq_len - self.pred_len + 1

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path,
                                          self.data_path))

        '''
        df_raw.columns: ['date', ...(other features), target feature]
        '''
        cols = list(df_raw.columns)
        cols.remove(self.target)
        cols.remove('date')
        df_raw = df_raw[['date'] + cols + [self.target]]
        num_train = int(len(df_raw) * 0.7)
        num_test = int(len(df_raw) * 0.2)
        num_vali = len(df_raw) - num_train - num_test
        border1s = [0, num_train - self.seq_len, len(df_raw) - num_test - self.seq_len]
        border2s = [num_train, num_train + num_vali, len(df_raw)]
        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]

        if self.set_type == 0:
            border2 = (border2 - self.seq_len) * self.percent // 100 + self.seq_len

        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]
        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        if self.scale:
            train_data = df_data[border1s[0]:border2s[0]]
            self.scaler.fit(train_data.values)
            data = self.scaler.transform(df_data.values)
        else:
            data = df_data.values

        df_stamp = df_raw[['date']][border1:border2]
        df_stamp['date'] = pd.to_datetime(df_stamp.date)
        if self.timeenc == 0:
            df_stamp['month'] = df_stamp.date.apply(lambda row: row.month, 1)
            df_stamp['day'] = df_stamp.date.apply(lambda row: row.day, 1)
            df_stamp['weekday'] = df_stamp.date.apply(lambda row: row.weekday(), 1)
            df_stamp['hour'] = df_stamp.date.apply(lambda row: row.hour, 1)
            data_stamp = df_stamp.drop(['date'], 1).values
        elif self.timeenc == 1:
            data_stamp = time_features(pd.to_datetime(df_stamp['date'].values), freq=self.freq)
            data_stamp = data_stamp.transpose(1, 0)

        self.data_x = data[border1:border2]
        self.data_y = data[border1:border2]
        self.data_stamp = data_stamp

    def __getitem__(self, index):
        feat_id = index // self.tot_len
        s_begin = index % self.tot_len

        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len
        seq_x = self.data_x[s_begin:s_end, feat_id:feat_id + 1]
        seq_y = self.data_y[r_begin:r_end, feat_id:feat_id + 1]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        seq_y_mark = self.data_stamp[r_begin:r_end]

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return (len(self.data_x) - self.seq_len - self.pred_len + 1) * self.enc_in

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_EFP_long(Dataset):
    # 用于一个批次内分割多个相同长度的数据
    def __init__(self, root_path, flag='train', size=None,
                 data_path='EFP_long.csv', target='hx', scale=True, freq='h', percent=100,
                 ):

        self.seq_len = size[0]
        self.label_len = size[1]
        self.pred_len = size[2]
        # init
        self.flag = flag
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.target = target
        self.scale = scale
        self.percent = percent

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path, self.data_path))
        '''
        df_raw.columns: ['date', ...(other features), target feature]
        '''
        cols = list(df_raw.columns)
        cols.remove(self.target)
        cols.remove('date')
        df_raw = df_raw[['date'] + cols + [self.target]]
        # 提取非时间特征
        self.feature_columns = [col for col in df_raw.columns if col not in ['date', 'batch_id', 'hh']]
        scaled_features = self.scaler.fit_transform(df_raw[self.feature_columns].values)
        df_raw = df_raw.copy()  # 深拷贝以防止影响原始数据
        df_raw[self.feature_columns] = scaled_features

        # 将 'date' 列转换为时间特征
        df_raw['date'] = pd.to_datetime(df_raw['date'])
        df_raw['month'] = df_raw['date'].dt.month
        df_raw['day'] = df_raw['date'].dt.day
        df_raw['hour'] = df_raw['date'].dt.hour
        self.time_features = ['month', 'day', 'hour']

        # 预处理数据：按批次分组，存储每个批次的序列
        self.batches = []
        for batch_id in df_raw['batch_id'].unique():
            batch_data = df_raw[df_raw['batch_id'] == batch_id].reset_index(drop=True)
            self.batches.append(batch_data)

        batch_num = len(self.batches)
        train_end = int(0.7 * batch_num)
        test_end = train_end + int(0.2 * batch_num)

        if self.flag == 'train':
            self.select_batches = self.batches[:train_end]
        elif self.flag == 'test':
            self.select_batches = self.batches[train_end:test_end]
        elif self.flag == 'val':
            self.select_batches = self.batches[test_end:]
        else:
            raise ValueError("flag must be 'train', 'val', or 'test'")

    def __getitem__(self, index):
        for batch in self.select_batches:
            max_start_idx = len(batch) - self.seq_len - self.pred_len
            if index <= max_start_idx:
                s_begin = index
                break
            else:
                index -= (max_start_idx + 1)
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len

        seq_x = batch.iloc[s_begin:s_end][self.feature_columns].values
        seq_y = batch.iloc[r_begin:r_end][self.target].values.reshape(-1, 1)  # TimeLLM, Informer
        # seq_y = batch.iloc[r_begin:r_end][self.feature_columns].values   # Autoformer FEDformer

        # 获取时间标记数据
        seq_x_mark = batch.iloc[s_begin:s_end][self.time_features].values
        seq_y_mark = batch.iloc[r_begin:r_end][self.time_features].values

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return sum(len(batch) - self.seq_len - self.pred_len + 1 for batch in self.select_batches)

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_EFP_RAG(Dataset):
    # 用于一个批次内分割多个相同长度的数据
    def __init__(self, root_path, flag='train', size=None,
                 data_path='EFP_long.csv', target='hx', scale=True, freq='h', percent=100,
                 ):

        self.seq_len = size[0]
        self.label_len = size[1]
        self.pred_len = size[2]
        # init
        self.flag = flag
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.target = target
        self.scale = scale
        self.percent = percent

        self.root_path = root_path
        self.data_path = data_path
        self.rag_path = 'Kmeans_batch.csv'
        # self.rag_path = 'EFP_long.csv'

        self.__read_data__()

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path, self.data_path))
        df_rag = pd.read_csv(os.path.join(self.root_path, self.rag_path))
        '''
        df_raw.columns: ['date', ...(other features), target feature]
        '''
        cols = list(df_raw.columns)
        cols.remove(self.target)
        cols.remove('date')
        df_raw = df_raw[['date'] + cols + [self.target]]
        # 提取非时间特征
        self.feature_columns = [col for col in df_raw.columns if col not in ['date', 'batch_id', 'hh']]

        scaled_features = self.scaler.fit_transform(df_raw[self.feature_columns].values)
        df_raw = df_raw.copy()  # 深拷贝以防止影响原始数据
        df_raw[self.feature_columns] = scaled_features

        scaled_rag = self.scaler.transform(df_rag[self.feature_columns].values)
        df_rag = df_rag.copy()
        df_rag[self.feature_columns] = scaled_rag

        # 将 'date' 列转换为时间特征
        df_raw['date'] = pd.to_datetime(df_raw['date'])
        df_raw['month'] = df_raw['date'].dt.month
        df_raw['day'] = df_raw['date'].dt.day
        df_raw['hour'] = df_raw['date'].dt.hour
        self.time_features = ['month', 'day', 'hour', 'hh']

        # 预处理数据：按批次分组，存储每个批次的序列
        self.batches = []
        for batch_id in df_raw['batch_id'].unique():
            batch_data = df_raw[df_raw['batch_id'] == batch_id].reset_index(drop=True)
            self.batches.append(batch_data)

        self.rag_batches = {batch_id: df_rag[df_rag['batch_id'] == batch_id].reset_index(drop=True)
                            for batch_id in df_rag['batch_id'].unique()}

        batch_num = len(self.batches)
        train_end = int(0.7 * batch_num)
        test_end = train_end + int(0.2 * batch_num)

        if self.flag == 'train':
            self.select_batches = self.batches[:train_end]
        elif self.flag == 'test':
            self.select_batches = self.batches[train_end:test_end]
        elif self.flag == 'val':
            self.select_batches = self.batches[test_end:]
        else:
            raise ValueError("flag must be 'train', 'val', or 'test'")

    def __getitem__(self, index):
        for batch in self.select_batches:
            max_start_idx = len(batch) - self.seq_len - self.pred_len
            if index <= max_start_idx:
                s_begin = index
                break
            else:
                index -= (max_start_idx + 1)
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len

        seq_x = batch.iloc[s_begin:s_end][self.feature_columns].values
        seq_y = batch.iloc[r_begin:r_end][self.target].values.reshape(-1, 1)  # TimeLLM, Informer
        # seq_y = batch.iloc[r_begin:r_end][self.feature_columns].values   # Autoformer FEDformer

        # 获取时间标记数据
        seq_x_mark = batch.iloc[s_begin:r_end][self.time_features].values
        seq_y_mark = batch.iloc[r_begin:r_end][self.time_features].values

        # 寻找最相似的样例
        # seq_x_flat = seq_x.flatten().reshape(1, -1)
        seq_x_flat = batch.iloc[s_begin:s_end][self.target].values.flatten()
        min_distance = float('inf')
        best_rag_batch = None

        for rag_batch_id, rag_batch in self.rag_batches.items():
            for i in range(len(rag_batch) - self.seq_len - self.pred_len):
                rag_seq = rag_batch.iloc[i:i + self.seq_len][self.target].values.flatten()
                distance = euclidean(seq_x_flat, rag_seq)
                if distance < min_distance:
                    min_distance = distance
                    rag_seq_best = rag_seq
                    best_rag_batch_first = rag_batch
                    best_rag_batch = rag_batch.iloc[i + self.seq_len: i + self.seq_len + self.pred_len][self.feature_columns].values
        # 拼接最相似样例数据到 seq_x
        if best_rag_batch is not None:
            seq_x = np.concatenate([seq_x, best_rag_batch], axis=0)

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return sum(len(batch) - self.seq_len - self.pred_len + 1 for batch in self.select_batches)

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_EFP_h2(Dataset):
    # 用于多个批次间长度拼接
    def __init__(self, root_path, flag='train', size=None,
                 features='MS', data_path='EFP_h2.csv',
                 target='hx', scale=True, inverse=False, timeenc=0, freq='h', cols=None):
        # size [seq_len, label_len, pred_len]
        # info
        if size == None:
            self.seq_len = 24 * 4 * 4
            self.label_len = 24 * 4
            self.pred_len = 24 * 4
        else:
            self.seq_len = size[0]
            self.label_len = size[1]
            self.pred_len = size[2]
        # init
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.features = features
        self.target = target
        self.scale = scale
        self.inverse = inverse
        self.timeenc = timeenc
        self.freq = freq

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

    def __read_data__(self):
        df_raw = pd.read_csv(os.path.join(self.root_path, self.data_path))

        total_data_points = 393 * 100
        border1s = [0, int(total_data_points * 0.7) - self.seq_len, int(total_data_points * 0.9) - self.seq_len]
        border2s = [int(total_data_points * 0.7), int(total_data_points * 0.9), total_data_points]
        border1 = border1s[self.set_type]
        border2 = border2s[self.set_type]

        if self.features == 'M' or self.features == 'MS':
            cols_data = df_raw.columns[1:]
            df_data = df_raw[cols_data]
        elif self.features == 'S':
            df_data = df_raw[[self.target]]

        # 对 data_x 进行标准化
        self.scaler_x = StandardScaler()
        if self.scale:
            train_data_x = df_data[border1s[0]:border2s[0]]
            self.scaler_x.fit(train_data_x.values)
            data_x = self.scaler_x.transform(df_data.values)
        else:
            data_x = df_data.values

        # 对 data_y（目标列）进行标准化
        target_data = df_raw[[self.target]].values
        self.scaler_y = StandardScaler()
        if self.scale:
            train_data_y = target_data[border1s[0]:border2s[0]]
            self.scaler_y.fit(train_data_y)
            data_y = self.scaler_y.transform(target_data)
        else:
            data_y = target_data

        df_stamp = df_raw[['date']][border1:border2]
        df_stamp['date'] = pd.to_datetime(df_stamp.date)
        if self.timeenc == 0:
            df_stamp['month'] = df_stamp.date.apply(lambda row: row.month, 1)
            df_stamp['day'] = df_stamp.date.apply(lambda row: row.day, 1)
            df_stamp['hour'] = df_stamp.date.apply(lambda row: row.hour, 1)
            data_stamp = df_stamp.drop(['date'], 1).values
        elif self.timeenc == 1:
            data_stamp = time_features(pd.to_datetime(df_stamp['date'].values), freq=self.freq)
            data_stamp = data_stamp.transpose(1, 0)

        self.data_x = data_x[border1:border2]
        self.data_y = data_y[border1:border2]
        self.data_stamp = data_stamp

    def __getitem__(self, index):
        s_begin = index
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len

        seq_x = self.data_x[s_begin:s_end]
        if self.inverse:
            seq_y = np.concatenate(
                [self.data_x[r_begin:r_begin + self.label_len], self.data_y[r_begin + self.label_len:r_end]], 0)
        else:
            seq_y = self.data_y[r_begin:r_end]
        seq_x_mark = self.data_stamp[s_begin:s_end]
        seq_y_mark = self.data_stamp[r_begin:r_end]

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return len(self.data_x) - self.seq_len - self.pred_len + 1

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)


class Dataset_EFP_each(Dataset):
    # 用于一个批次内分割多个相同长度的数据
    def __init__(self, root_path, flag='train', size=None,
                 data_path='EFP_long.csv', target='hx', scale=True, freq='h', percent=100,
                 ):

        self.seq_len = size[0]
        self.label_len = size[1]
        self.pred_len = size[2]
        # init
        self.flag = flag
        assert flag in ['train', 'test', 'val']
        type_map = {'train': 0, 'val': 1, 'test': 2}
        self.set_type = type_map[flag]

        self.target = target
        self.scale = scale
        self.percent = percent

        self.root_path = root_path
        self.data_path = data_path
        self.__read_data__()

    def __read_data__(self):
        self.scaler = StandardScaler()
        df_raw = pd.read_csv(os.path.join(self.root_path, self.data_path))
        '''
        df_raw.columns: ['date', ...(other features), target feature]
        '''
        cols = list(df_raw.columns)
        cols.remove(self.target)
        cols.remove('date')
        df_raw = df_raw[['date'] + cols + [self.target]]
        # 提取非时间特征
        self.feature_columns = [col for col in df_raw.columns if col not in ['date', 'batch_id', 'hh']]
        scaled_features = self.scaler.fit_transform(df_raw[self.feature_columns].values)
        df_raw = df_raw.copy()  # 深拷贝以防止影响原始数据
        df_raw[self.feature_columns] = scaled_features

        # 将 'date' 列转换为时间特征
        df_raw['date'] = pd.to_datetime(df_raw['date'])
        df_raw['month'] = df_raw['date'].dt.month
        df_raw['day'] = df_raw['date'].dt.day
        df_raw['hour'] = df_raw['date'].dt.hour
        self.time_features = ['month', 'day', 'hour']

        # 预处理数据：按批次分组，存储每个批次的序列
        self.batches = []
        for batch_id in df_raw['batch_id'].unique():
            batch_data = df_raw[df_raw['batch_id'] == batch_id].reset_index(drop=True)
            # 裁剪每个批次的数据，只保留前 seq_len 长度
            if len(batch_data) >= self.seq_len + self.pred_len:
                batch_data = batch_data[:self.seq_len + self.pred_len]
                self.batches.append(batch_data)

        batch_num = len(self.batches)
        train_end = int(0.7 * batch_num)
        test_end = train_end + int(0.2 * batch_num)

        if self.flag == 'train':
            self.select_batches = self.batches[:train_end]
        elif self.flag == 'test':
            self.select_batches = self.batches[train_end:test_end]
        elif self.flag == 'val':
            self.select_batches = self.batches[test_end:]
        else:
            raise ValueError("flag must be 'train', 'val', or 'test'")

    def __getitem__(self, index):
        batch = self.select_batches[index]
        s_begin = 0
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = r_begin + self.label_len + self.pred_len

        seq_x = batch.iloc[s_begin:s_end][self.feature_columns].values
        seq_y = batch.iloc[r_begin:r_end][self.target].values.reshape(-1, 1)  # TimeLLM, Informer
        # seq_y = batch.iloc[r_begin:r_end][self.feature_columns].values   # Autoformer FEDformer

        # 获取时间标记数据
        seq_x_mark = batch.iloc[s_begin:s_end][self.time_features].values
        seq_y_mark = batch.iloc[r_begin:r_end][self.time_features].values

        return seq_x, seq_y, seq_x_mark, seq_y_mark

    def __len__(self):
        return len(self.select_batches)


class Dataset_M4(Dataset):
    def __init__(self, root_path, flag='pred', size=None,
                 features='S', data_path='ETTh1.csv',
                 target='OT', scale=False, inverse=False, timeenc=0, freq='15min',
                 seasonal_patterns='Yearly'):
        self.features = features
        self.target = target
        self.scale = scale
        self.inverse = inverse
        self.timeenc = timeenc
        self.root_path = root_path

        self.seq_len = size[0]
        self.label_len = size[1]
        self.pred_len = size[2]

        self.seasonal_patterns = seasonal_patterns
        self.history_size = M4Meta.history_size[seasonal_patterns]
        self.window_sampling_limit = int(self.history_size * self.pred_len)
        self.flag = flag

        self.__read_data__()

    def __read_data__(self):
        # M4Dataset.initialize()
        if self.flag == 'train':
            dataset = M4Dataset.load(training=True, dataset_file=self.root_path)
        else:
            dataset = M4Dataset.load(training=False, dataset_file=self.root_path)
        training_values = np.array(
            [v[~np.isnan(v)] for v in
             dataset.values[dataset.groups == self.seasonal_patterns]])  # split different frequencies
        self.ids = np.array([i for i in dataset.ids[dataset.groups == self.seasonal_patterns]])
        self.timeseries = [ts for ts in training_values]

    def __getitem__(self, index):
        insample = np.zeros((self.seq_len, 1))
        insample_mask = np.zeros((self.seq_len, 1))
        outsample = np.zeros((self.pred_len + self.label_len, 1))
        outsample_mask = np.zeros((self.pred_len + self.label_len, 1))  # m4 dataset

        sampled_timeseries = self.timeseries[index]
        cut_point = np.random.randint(low=max(1, len(sampled_timeseries) - self.window_sampling_limit),
                                      high=len(sampled_timeseries),
                                      size=1)[0]

        insample_window = sampled_timeseries[max(0, cut_point - self.seq_len):cut_point]
        insample[-len(insample_window):, 0] = insample_window
        insample_mask[-len(insample_window):, 0] = 1.0
        outsample_window = sampled_timeseries[
                           cut_point - self.label_len:min(len(sampled_timeseries), cut_point + self.pred_len)]
        outsample[:len(outsample_window), 0] = outsample_window
        outsample_mask[:len(outsample_window), 0] = 1.0
        return insample, outsample, insample_mask, outsample_mask

    def __len__(self):
        return len(self.timeseries)

    def inverse_transform(self, data):
        return self.scaler.inverse_transform(data)

    def last_insample_window(self):
        """
        The last window of insample size of all timeseries.
        This function does not support batching and does not reshuffle timeseries.

        :return: Last insample window of all timeseries. Shape "timeseries, insample size"
        """
        insample = np.zeros((len(self.timeseries), self.seq_len))
        insample_mask = np.zeros((len(self.timeseries), self.seq_len))
        for i, ts in enumerate(self.timeseries):
            ts_last_window = ts[-self.seq_len:]
            insample[i, -len(ts):] = ts_last_window
            insample_mask[i, -len(ts):] = 1.0
        return insample, insample_mask
