from django.contrib import admin

from . import models

for m in (models.User, models.ConsentRecord, models.Wallet, models.FaceEnrollment, models.Device,
          models.ItemClass, models.SortingEvent, models.Payout):
    admin.site.register(m)
