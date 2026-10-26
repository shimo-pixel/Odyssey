"""Document stage progress and upload-to-remote tracking correlation."""
from unittest.mock import AsyncMock

import pytest

from prds.kb.routes import _document_progress, _refresh_remote_statuses, _doc_out
from prds.storage.models import KbDocument


@pytest.mark.parametrize('stage,percent,estimated', [
    ('pending', 0, True), ('parsing', 15, True), ('analyzing', 40, True),
    ('preprocessed', 55, True), ('processing', 65, True),
    ('processed', 100, False), ('failed', None, False), ('error', None, False),
    ('unknown', None, True),
])
def test_stage_percent_is_explicitly_estimated_until_completed(stage, percent, estimated):
    assert _document_progress(stage) == (percent, estimated)


async def test_upload_without_doc_id_follows_track_id_through_processing():
    row = KbDocument(id='local', category_id='kb', filename='sample.pdf', track_id='track',
                     status='pending', size=100)
    client = AsyncMock()
    for stage, percent in [('parsing', 15), ('processing', 65), ('processed', 100)]:
        client.list_documents.return_value = {'statuses': {stage: [
            {'id': 'remote', 'track_id': 'track', 'status': stage}
        ]}}
        await _refresh_remote_statuses(client, [row], 'kb')
        assert row.doc_id == 'remote'
        public = _doc_out(row)
        assert public.processing_stage == stage and public.progress_pct == percent
        assert public.progress_is_estimated is (stage != 'processed')


async def test_progress_is_not_copied_from_another_document():
    row = KbDocument(id='local', category_id='kb', filename='sample.pdf', track_id='ours',
                     status='pending', size=100)
    client = AsyncMock()
    client.list_documents.return_value = {'statuses': {'processed': [
        {'id': 'other', 'track_id': 'someone-else', 'status': 'processed'}
    ]}}
    await _refresh_remote_statuses(client, [row], 'kb')
    assert row.doc_id is None and row.status == 'pending'
