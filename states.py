from vkbottle import BaseStateGroup

class AddProductSG(BaseStateGroup):
    WAITING_NAME = 0
    WAITING_DESCRIPTION = 1
    WAITING_PRICE = 2
    WAITING_PHOTO = 3

class DeleteProductSG(BaseStateGroup):
    WAITING_ID = 0

class ManagePhotoSG(BaseStateGroup):
    WAITING_PRODUCT_ID = 0
    WAITING_PHOTO_INDEX = 1
