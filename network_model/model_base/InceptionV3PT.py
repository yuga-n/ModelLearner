import torchvision
from torchvision.models.inception import inception_v3
import torch
from torch.nn import Sequential, Dropout, Linear, ReLU, Softmax, Sigmoid
from util_types import types_of_loco
from torch.serialization import load

def builder(
        class_num: int,
        img_size: types_of_loco.input_img_size = 28,
        channels: int = 3,
) -> torch.nn.Module:
    base_model = inception_v3(pretrained=True)
    num_ftrs = base_model.fc.in_features
    if class_num > 2:
        base_model.fc = Sequential(
            Dropout(0.2),
            Linear(num_ftrs, class_num),
            Softmax(dim=1)
        )
        base_model.AuxLogits.fc = Sequential(
            Dropout(0.2),
            Linear(768, class_num),
            Softmax(dim=1)
        )
    else:
        base_model.classifier = Sequential(
            Dropout(0.2),
            Linear(num_ftrs, 1),
            Sigmoid()
        )
        base_model.AuxLogits.fc = Sequential(
            Dropout(0.2),
            Linear(768, class_num),
            Softmax(dim=1)
        )
    return base_model

