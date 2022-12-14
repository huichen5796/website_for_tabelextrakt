import sys
import json
from functions import Search, TiltCorrection, SizeNormalize, PositionTable, GetTableZone, SaveTable, SaveExcel
import re
import numpy as np
import cv2
import os
import torch
from file_read_backwards import FileReadBackwards
import torch.nn as nn
import torchvision
from elasticsearch import Elasticsearch
es = Elasticsearch()


class DenseNet(nn.Module):
    def __init__(self, pretrained=True, requires_grad=True):
        super(DenseNet, self).__init__()
        denseNet = torchvision.models.densenet121(pretrained=True).features
        self.densenet_out_1 = torch.nn.Sequential()
        self.densenet_out_2 = torch.nn.Sequential()
        self.densenet_out_3 = torch.nn.Sequential()

        for x in range(8):
            self.densenet_out_1.add_module(str(x), denseNet[x])
        for x in range(8, 10):
            self.densenet_out_2.add_module(str(x), denseNet[x])

        self.densenet_out_3.add_module(str(10), denseNet[10])

        if not requires_grad:
            for param in self.parameters():
                param.requires_grad = False

    def forward(self, x):

        out_1 = self.densenet_out_1(x)  # torch.Size([1, 256, 64, 64])
        out_2 = self.densenet_out_2(out_1)  # torch.Size([1, 512, 32, 32])
        out_3 = self.densenet_out_3(out_2)  # torch.Size([1, 1024, 32, 32])
        return out_1, out_2, out_3


class TableDecoder(nn.Module):
    def __init__(self, channels, kernels, strides):
        super(TableDecoder, self).__init__()
        self.conv_7_table = nn.Conv2d(
            in_channels=256,
            out_channels=256,
            kernel_size=kernels[0],
            stride=strides[0])
        self.upsample_1_table = nn.ConvTranspose2d(
            in_channels=256,
            out_channels=128,
            kernel_size=kernels[1],
            stride=strides[1])
        self.upsample_2_table = nn.ConvTranspose2d(
            in_channels=128 + channels[0],
            out_channels=256,
            kernel_size=kernels[2],
            stride=strides[2])
        self.upsample_3_table = nn.ConvTranspose2d(
            in_channels=256 + channels[1],
            out_channels=1,
            kernel_size=kernels[3],
            stride=strides[3])

    def forward(self, x, pool_3_out, pool_4_out):
        x = self.conv_7_table(x)  # [1, 256, 32, 32]
        out = self.upsample_1_table(x)  # [1, 128, 64, 64]
        out = torch.cat((out, pool_4_out), dim=1)  # [1, 640, 64, 64]
        out = self.upsample_2_table(out)  # [1, 256, 128, 128]
        out = torch.cat((out, pool_3_out), dim=1)  # [1, 512, 128, 128]
        out = self.upsample_3_table(out)  # [1, 1, 1024, 1024]
        return out


class TableNet(nn.Module):
    def __init__(self, encoder='densenet', use_pretrained_model=True, basemodel_requires_grad=True):
        super(TableNet, self).__init__()

        self.base_model = DenseNet(
            pretrained=use_pretrained_model, requires_grad=basemodel_requires_grad)
        self.pool_channels = [512, 256]
        self.in_channels = 1024
        self.kernels = [(1, 1), (1, 1), (2, 2), (16, 16)]
        self.strides = [(1, 1), (1, 1), (2, 2), (16, 16)]

        # common layer
        self.conv6 = nn.Sequential(
            nn.Conv2d(in_channels=self.in_channels,
                      out_channels=256, kernel_size=(1, 1)),
            nn.ReLU(inplace=True),
            nn.Dropout(0.8),
            nn.Conv2d(in_channels=256, out_channels=256, kernel_size=(1, 1)),
            nn.ReLU(inplace=True),
            nn.Dropout(0.8))

        self.table_decoder = TableDecoder(
            self.pool_channels, self.kernels, self.strides)

    def forward(self, x):

        pool_3_out, pool_4_out, pool_5_out = self.base_model(x)
        conv_out = self.conv6(pool_5_out)  # [1, 256, 32, 32]
        # torch.Size([1, 1, 1024, 1024])
        table_out = self.table_decoder(conv_out, pool_3_out, pool_4_out)
        return table_out


def Run(line, model):
    info = eval(line.split('\n')[0])
    blob_path = 'assets' + info['path']
    file_name = info['fileName'].split('/')[-1]

    with open(blob_path, 'rb') as f:

        image = np.frombuffer(f.read(), np.int8)
        image = cv2.imdecode(image, cv2.IMREAD_COLOR)

        #cv2.imshow('', image)
        # cv2.waitKey()

    shape_list = list(image.shape)
    if len(shape_list) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    image_rotate = TiltCorrection(image)  # got gray
    img_3channel = cv2.cvtColor(
        image_rotate, cv2.COLOR_GRAY2BGR)  # gray to 3 channel

    img_1024 = SizeNormalize(img_3channel)
    table_boundRect = PositionTable(
        img_1024, file_name, model)  # unet besser
    table_zone = GetTableZone(table_boundRect, img_1024)
    img_path = 'assets\\imageShow\\' + file_name
    for nummer, table in enumerate(table_zone):
        SaveTable(nummer, table, img_path, [],
                  model, [])  # densecol besser

    relation = {
        'file': file_name,
        'tableNumber': str(len(table_zone))
    }

    with open('assets\\imageShow\\relation.txt', 'a+') as f:
        f.write(str(relation)+'\n')


def receivePara():
    msg = sys.argv[1]
    msg = eval(msg)
    #msg ={ 'todo': 'cleanAll'}
    if msg['todo'] == 'run': # The pictures recorded in the txt file ('assets\uploads\originalName.txt') are processed with the function ('Run()') in turn to extract the tables
        try:
            if os.path.getsize('assets\\uploads\\originalName.txt') == 0:
                res = {
                    'massage': 'noData'
                }

                print(json.dumps(res))
            else:
                model = msg['model']
                # deduplication of txt
                with FileReadBackwards('assets\\uploads\\originalName.txt', encoding="utf-8") as fb:
                    fileName_list = []
                    for line in fb:
                        try:
                            # if re.search(msg['file'], line) != None:
                            fileName = eval(line.split('\n')[0])[
                                'fileName'].split('/')[-1]
                            if fileName not in fileName_list:
                                fileName_list.append(fileName)
                                Run(line, model)
                        except:
                            continue

                res = {
                    'massage': 'success'
                }
                fileName_list = []
                print(json.dumps(res))

        except:
            res = {
                'massage': 'error'
            }
            print(json.dumps(res))

    if msg['todo'] == 'search': # Search table data by uniqueID and output table data as JSON {'':'','':'',..}
        try:
            results = Search(msg['idx'], msg['label'])
            results = json.loads(results)['hits']['hits']
            table = {}

            for i, result in enumerate(results):
                del result['_source']['uniqueId']
                del result['_source']['fileName']
                table['col%s' % i] = result['_source']

            print(json.dumps({
                'massage': 'success',
                'datas': table,
                'label': msg['label']
            }))
        except:
            print(json.dumps({
                'massage': 'error',
            }))

    if msg['todo'] == 'searchLabel': # Search the database for all table uniqueID and output the uniqueIDs as LIST ['','','',..]

        try:
            uniqueId_list = []
            res = Search('table', 'all')
            res = json.loads(res)['hits']['hits']
            for ress in res:
                uniqueId_list.append(ress['_source']['uniqueId'])
            uniqueId_list = list(set(uniqueId_list))

            print(uniqueId_list)
        except:
            print('["error"]')

    if msg['todo'] == 'upload': # Write the correspondence between the binary file name and the original image name into the txt file ('assets\uploads\originalName.txt'), output JSON
        try:
            with open('assets/uploads/originalName.txt', 'a+') as f:
                f.write(str(msg).replace('\\', '/').replace('//',
                        '/').split('/assets')[-1]+'\n')
            print(json.dumps({'massage': 'success',
                              'fileName': '["'+msg['fileName']+'"]'}))
        except:
            print(json.dumps({'massage': 'error', }))

    if msg['todo'] == 'uploadStapel': # see oben
        try:
            datas = list(msg['data'])
            with open('assets/uploads/originalName.txt', 'a+') as f:
                for data in datas:
                    data = eval(str(data).replace(
                        '\\', '/').replace('//', '/'))
                    data['fileName'] = data['fileName'].split('/')[-1]

                    f.write(str(data)+'\n')
            files = str([(data)['fileName'].split('/')[-1] for data in datas])
            print(json.dumps({'massage': 'success',
                              'files': files,
                              }))
        except:
            print(json.dumps({'massage': 'error', }))

    if msg['todo'] == 'seeDetail': # Get the corresponding image processing results according to the records in the txt file ('assets\imageShow\relation.txt'), output JSON
        try:
            f = open('assets/uploads/originalName.txt', 'r')
            path_list = []
            for line in f.readlines():
                if re.search(msg['image'], line) != None:
                    path = eval(line.split('\n')[0])
                    path_list.append(path)

            f = open('assets\\imageShow\\relation.txt', 'r')
            info_list = []
            for line in f.readlines():
                if re.search(msg['image'], line) != None:
                    info = eval(line.split('\n')[0])
                    info_list.append(info)
            resInfo = {
                'massage': 'success',
                'fileName': msg['image'],
                'path': path_list[-1]['path'],
            }
            number = int(info_list[-1]['tableNumber'])
            for i in range(1, number+1):
                resInfo['the_%sst_table_of_%s' % (
                    i, msg['image'])] = "imageShow/table_%s_of_%s" % (i, msg['image'])

            print(json.dumps(resInfo))

        except:
            print(json.dumps({'massage': "error"}))

    if msg['todo'] == 'cleanAll': # output JSON
        try:
            for file in os.listdir('assets/uploads'):
                file = os.path.join('assets/uploads', file)
                os.remove(file)
            f = open('assets/uploads/originalName.txt', 'w')
            f.close()
            for file in os.listdir('assets/imageShow'):
                file = os.path.join('assets/imageShow', file)
                os.remove(file)
            f = open('assets/imageShow/relation.txt', 'w')
            f.close()
            for file in os.listdir('assets/excelStore'):
                file = os.path.join('assets/excelStore', file)
                os.remove(file)

            # deletes whole index
            es.indices.delete(index='table', ignore=[400, 404])

            print(json.dumps({'massage': 'success'}))
        except:
            print(json.dumps({'massage': 'error'}))

    if msg['todo'] == 'cleanEla': # output JSON
        try:
            # deletes whole index
            es.indices.delete(index='table', ignore=[400, 404])

            print(json.dumps({'massage': 'success'}))
        except:
            print(json.dumps({'massage': 'error'}))

    if msg['todo'] == 'continue': # Get processing progress and all image names, output JSON
        try:
            file_list = []
            with open('assets/uploads/originalName.txt', 'r') as f:
                for line in f:
                    file_list.append(eval(line.split('\n')[0])['fileName'])
            file_list = list(set(file_list))

            total = len(file_list)

            f = open('assets/imageShow/relation.txt', 'r')
            done_list = [eval(do.split('\n')[0])['file']
                         for do in f.readlines()]
            done_list = list(set(done_list))
            done = len(done_list)
            f.close()

            progress = str(done*100//total) + '%'

            if len(file_list) != 0:
                print(json.dumps({
                    'massage': 'success',
                    'fileName': file_list,
                    'progress': progress,

                }))
            else:
                print(json.dumps({
                    'massage': 'error',
                }))
        except:
            print(json.dumps({'massage': 'error', }))

    if msg['todo'] == 'continueRun': # Continue processing unprocessed images, output JSON
        try:
            file_list = []
            with open('assets/uploads/originalName.txt', 'r') as f:
                for line in f:
                    file_list.append(eval(line.split('\n')[0])['fileName'])
            file_list = list(set(file_list))

            total = len(file_list)

            f = open('assets/imageShow/relation.txt', 'r')
            done_list = [eval(do.split('\n')[0])['file']
                         for do in f.readlines()]
            done_list = list(set(done_list))
            done = len(done_list)
            f.close()

            progress = str(done*100//total) + '%'

            todo_list = [todo for todo in file_list if todo not in done_list]
            todo_list = list(set(todo_list))
            # print(todo_list)
            model = 'densenet'
            # deduplication of txt
            # print(todo_list)
            for todo in todo_list:

                try:
                    with FileReadBackwards('assets\\uploads\\originalName.txt', encoding="utf-8") as fb:
                        for line in fb:
                            if eval(line.split('\n')[0])['fileName'].split('/')[-1] == todo:
                                # print(todo)
                                Run(line, model)
                except:
                    continue

            print(json.dumps({'massage': 'success',}))
        except:
            print(json.dumps({'massage': 'error', }))

    if msg['todo'] == 'saveExcel': # output JSON
        try:

            tableId = msg['tableId']

            saveName = SaveExcel(tableId)

            res = {
                'massage': 'success',
                'excelName': saveName
            }
            print(json.dumps(res))
        except:
            res = {
                'massage': 'error',
            }
            print(json.dumps(res))

    if msg['todo'] == 'getProgress': # Get processing progress
        try:
            total = len(os.listdir('assets/uploads'))

            f = open('assets/imageShow/relation.txt', 'r')
            done = len(f.readlines())
            f.close()

            progress = str(done*100//total) + '%'

            res = {
                'massage': 'success',
                'progress': progress
            }
            print(json.dumps(res))
        except:
            print(json.dumps({'massage': 'error'}))


receivePara()
