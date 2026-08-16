import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
        ('followups', '0002_advisorcallbackrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='WhatsAppOptOut',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mobile', models.CharField(max_length=20)),
                ('source', models.CharField(blank=True, default='keyword', max_length=40)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.tenant')),
            ],
            options={
                'db_table': 'whatsapp_opt_outs',
            },
        ),
        migrations.AddConstraint(
            model_name='whatsappoptout',
            constraint=models.UniqueConstraint(fields=('tenant', 'mobile'), name='uq_whatsapp_optout_tenant_mobile'),
        ),
    ]
