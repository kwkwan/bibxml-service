import json
import re
from typing import List, Any
from unittest import TestCase

from django.core.management import call_command
from django.db.models import QuerySet, Q

from main.exceptions import RefNotFoundError
from main.models import RefData
from main.query import (
    search_refs_relaton_field,
    list_refs,
    list_doctypes,
    search_refs_docids,
    build_citation_for_docid,
    build_search_results,
    get_indexed_item,
    get_indexed_ref_by_query,
    search_refs_relaton_struct,
)
from main.types import CompositeSourcedBibliographicItem, IndexedBibliographicItem


class QueryTestCase(TestCase):
    """
    Test cases for query.py
    """

    def setUp(self) -> None:
        # load fixtures (fixtures file is in a different app, thus it needs to be loaded manually)
        call_command("loaddata", "xml2rfc_compat/fixtures/test_refdata.json")

        with open("xml2rfc_compat/fixtures/test_refdata.json", "r") as f:
            self.json_fixtures = json.load(f)

    def _get_list_of_docids_for_dataset_from_fixture(
        self, dataset="rfcs"
    ) -> List[dict[Any, Any]]:
        """
        Retrieves a list of docids for a given dataset given as parameter
        from the fixtures used to test this component.
        """
        return [
            item["fields"]["body"]["docid"]
            for item in self.json_fixtures
            if item["fields"]["dataset"] == dataset
        ][0]

    def test_list_refs(self):
        dataset_id = "rfcs"
        rfcs_refs_queryset = list_refs(dataset_id)
        self.assertGreater(rfcs_refs_queryset.count(), 0)

        non_rfcs_queryset = rfcs_refs_queryset.exclude(dataset__iexact=dataset_id)
        self.assertEqual(non_rfcs_queryset.count(), 0)

    def test_list_doctypes(self):
        doctypes = list_doctypes()
        self.assertIsInstance(doctypes, list)
        self.assertGreater(len(doctypes), 0)
        self.assertIsInstance(doctypes[0], tuple)

    def test_search_refs_relaton_struct(self):
        limit = 2
        objs = [
            {"docid": [{"id": self._get_list_of_docids_for_dataset_from_fixture()[0].get("id")}]},
            {"docid": [{"id": self._get_list_of_docids_for_dataset_from_fixture("misc")[0].get("id")}]},
            {"docid": [{"id": self._get_list_of_docids_for_dataset_from_fixture("ieee")[0].get("id")}]},
        ]
        refs = search_refs_relaton_struct(*objs, limit=limit)
        self.assertIsInstance(refs, QuerySet[RefData])
        self.assertGreater(refs.count(), 0)
        self.assertLessEqual(refs.count(), limit)

    def test_search_refs_relaton_struct_empty_results(self):
        """
        Test that search_refs_relaton_struct returns an empty list of
        results when called with an empty list of objs.
        """
        objs: List[Any] = []
        refs = search_refs_relaton_struct(*objs)
        self.assertIsInstance(refs, QuerySet[RefData])
        self.assertEqual(refs.count(), 0)

    def test_search_refs_relaton_field(self):
        docids = self._get_list_of_docids_for_dataset_from_fixture("rfcs")
        docid = next(docid["id"] for docid in docids if docid.get("scope") == "anchor")

        limit = 2
        refs = search_refs_relaton_field(
            {
                "docid[*]": '@.id == "%s"' % re.escape(docid),
            },
            limit=limit,
            exact=True,
        )
        self.assertIsInstance(refs, QuerySet[RefData])
        self.assertGreater(refs.count(), 0)
        self.assertLessEqual(refs.count(), limit)

    def test_search_refs_relaton_field_without_field_queries(self):
        """
        The function search_refs_relaton_field should return an empty
        QuerySet if no query is passed as parameter.
        """
        refs = search_refs_relaton_field()
        self.assertIsInstance(refs, QuerySet[RefData])
        self.assertEqual(refs.count(), 0)

    def test_search_refs_docids(self):
        docids = self._get_list_of_docids_for_dataset_from_fixture()
        ids = [item["id"] for item in docids]
        refs = search_refs_docids(*ids)
        self.assertIsInstance(refs, QuerySet[RefData])
        self.assertGreater(refs.count(), 0)

    def test_build_citation_for_docid(self):
        docids = self._get_list_of_docids_for_dataset_from_fixture()
        for docid in docids:
            id, doctype = docid["id"], docid["type"]
            citation = build_citation_for_docid(id, doctype)
            self.assertIsInstance(citation, CompositeSourcedBibliographicItem)

    def test_build_citation_for_nonexistent_docid(self):
        """
        The function build_citation_for_docid should :raise RefNotFoundError:
        if a combination of non-existing id and reference is passed as parameter.
        """
        id, doctype = "NONEXISTENTID", "NONEXISTENTTYPE"
        with self.assertRaises(RefNotFoundError):
            build_citation_for_docid(id, doctype)

    def test_build_citation_for_docid_strict_is_false(self):
        """
        Test build_citation_for_docid using strict=False. Validation
        errors should not be triggered, however a representation should
        be returned anyway.
        """
        docids = self._get_list_of_docids_for_dataset_from_fixture()
        for docid in docids:
            id, doctype = docid["id"], docid["type"]
            citation = build_citation_for_docid(id, doctype, strict=False)
            self.assertIsInstance(citation, CompositeSourcedBibliographicItem)

    def test_build_search_results(self):
        docids = self._get_list_of_docids_for_dataset_from_fixture("misc")
        docid = next(docid["id"] for docid in docids if docid.get("scope") == "anchor")

        limit = 10
        refs = search_refs_relaton_field(
            {
                "docid[*]": '@.id == "%s"' % re.escape(docid),
            },
            limit=limit,
            exact=True,
        )

        found_items = build_search_results(refs)
        self.assertIsInstance(found_items, list)
        self.assertGreater(len(found_items), 0)

    def test_build_search_empty_results(self):
        """
        Test that build_search_results returns an empty list of
        results with a query that does not match any item.
        """
        refs = search_refs_relaton_field(
            {
                "docid[*]": '@.id == "%s"' % re.escape("NONEXISTENTID"),
            },
            exact=True,
        )

        found_items = build_search_results(refs)
        self.assertIsInstance(found_items, list)
        self.assertEqual(len(found_items), 0)

    def test_get_indexed_item(self):
        dataset_object = [
            item["fields"]
            for item in self.json_fixtures
            if item["fields"]["dataset"] == "rfcs"
        ][0]
        dataset, ref = dataset_object["dataset"], dataset_object["ref"]
        indexed_item = get_indexed_item(dataset, ref)
        self.assertIsInstance(indexed_item, IndexedBibliographicItem)

    def test_get_indexed_item_strict_is_false(self):
        """
        The dataset_object of reference for this test contains
        some formatting errors. Using strict=False, validation
        errors should not be triggered, however a
        representation should be returned anyway.
        """
        dataset_ref = "RFC4035"
        dataset_object = [
            item["fields"]
            for item in self.json_fixtures
            if item["fields"]["dataset"] == "rfcs"
            and item["fields"]["ref"] == dataset_ref
        ][0]
        dataset, ref = dataset_object["dataset"], dataset_object["ref"]
        indexed_item = get_indexed_item(dataset, ref, strict=False)
        self.assertIsInstance(indexed_item, IndexedBibliographicItem)

    def test_get_indexed_ref_by_query(self):
        dataset_object = [
            item["fields"]
            for item in self.json_fixtures
            if item["fields"]["dataset"] == "rfcs"
        ][0]
        dataset, ref = dataset_object["dataset"], dataset_object["ref"]
        data = get_indexed_ref_by_query(dataset, Q(ref__iexact=ref))
        self.assertIsInstance(data, RefData)

    def test_get_indexed_ref_by_query_nonexistent_ref(self):
        """
        The function get_indexed_ref_by_query should :raise RefNotFoundError:
        if a combination of non-existing dataset and reference is passed as parameter.
        """
        dataset, ref = "NONEXISTING_DATASET", "NONEXISTING_REF"
        with self.assertRaises(RefNotFoundError):
            get_indexed_ref_by_query(dataset, Q(ref__iexact=ref))

    def test_get_indexed_ref_by_query_multiple_ref_found(self):
        """
        The function get_indexed_ref_by_query should :raise RefNotFoundError:
        if multiple instances are found given the query passed as parameter.
        """
        dataset = "rfcs"
        with self.assertRaises(RefNotFoundError):
            get_indexed_ref_by_query(dataset, Q())
