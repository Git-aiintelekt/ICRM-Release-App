"""Jira issues with their seed data and table entries, on the existing jira_* tables (unmanaged)."""
from django.db import models
from django.utils import timezone


class JiraIssue(models.Model):
    jira_id = models.CharField("Jira ID", max_length=20, primary_key=True)
    description = models.CharField(max_length=1000, null=True, blank=True)
    link = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "jira_issue"
        ordering = ["jira_id"]
        verbose_name = "Jira issue"

    def __str__(self):
        return self.jira_id

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class JiraSeedEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    jira_issue = models.ForeignKey(JiraIssue, on_delete=models.CASCADE, related_name="seeds", db_column="jira_id")
    type = models.CharField(max_length=20)
    seed_ref = models.CharField(max_length=150, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "jira_seed_entry"
        ordering = ["display_order", "id"]
        verbose_name = "seed entry"
        verbose_name_plural = "seed entries"

    def __str__(self):
        return self.seed_ref or f"{self.type} #{self.id}"


class JiraTableEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    jira_issue = models.ForeignKey(JiraIssue, on_delete=models.CASCADE, related_name="tables", db_column="jira_id")
    type = models.CharField(max_length=20)
    table_name = models.CharField(max_length=255, null=True, blank=True)
    primary_key_field = models.CharField(max_length=255, null=True, blank=True)
    primary_key_value = models.CharField(max_length=500, null=True, blank=True)
    name_description = models.CharField(max_length=500, null=True, blank=True)
    seed_ref = models.CharField(max_length=150, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "jira_table_entry"
        ordering = ["display_order", "id"]
        verbose_name = "table entry"
        verbose_name_plural = "table entries"

    def __str__(self):
        return self.table_name or f"{self.type} #{self.id}"
