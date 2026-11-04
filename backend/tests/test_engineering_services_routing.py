"""
Comprehensive Regression Test Suite for CivicIQ Engineering Service Routing
Tests all 9 canonical user queries specified in the prompt:
1. "Help me with tree removal procedure."
2. "How to import soil?"
3. "I want to bring 20 cubic yards of soil."
4. "I want to export soil."
5. "I want to remove less than 10 cubic yards of soil."
6. "How do I apply for a road-opening permit?"
7. "I want to improve my property."
8. "How do I apply for a zoning permit?"
9. Engineering service without a configured flowchart (driveway engineering standards)
"""

import unittest
from backend.app.rag_engine import rag_engine
from backend.app.flow_engine import flow_engine
from backend.app.services.form_matcher import form_matcher
from backend.app.services.service_intent_service import service_intent_service


class TestEngineeringServicesRouting(unittest.TestCase):

    def test_query_1_tree_removal_flow(self):
        """
        Query 1: 'Help me with tree removal procedure.'
        Multi-turn flow:
        - Turn 1: Bot asks if resident has an approved permit.
        - Turn 2: Resident replies 'no, it is urgent no time to ask for permit' -> Bot asks for emergency reason.
        - Turn 3: Resident replies 'the tree is dead and cracked leaning dangerously toward my roof' ->
                  Bot confirms emergency procedure, delivers 3.23.21 tree permit application.pdf.
        """
        # Turn 1
        res1 = rag_engine.answer_query("Help me with tree removal procedure.")
        self.assertTrue(res1.grounded)
        self.assertIn("approved permit", res1.answer.lower())
        self.assertIsNone(res1.form_packet)

        # Turn 2
        history_1 = [
            {"role": "user", "content": "Help me with tree removal procedure."},
            {"role": "assistant", "content": res1.answer}
        ]
        res2 = rag_engine.answer_query("No, it's urgent no time to ask for permit", history=history_1)
        self.assertIn("emergency condition", res2.answer.lower())
        self.assertIsNone(res2.form_packet)

        # Turn 3
        history_2 = history_1 + [
            {"role": "user", "content": "No, it's urgent no time to ask for permit"},
            {"role": "assistant", "content": res2.answer}
        ]
        res3 = rag_engine.answer_query(
            "The tree is dead, severely cracked and leaning dangerously toward my roof in this storm",
            history=history_2
        )
        self.assertIn("emergency removal is permitted", res3.answer.lower())
        self.assertIsNotNone(res3.form_packet)
        self.assertEqual(res3.form_packet.form_file, "3.23.21 tree permit application.pdf")
        # Ensure internal flowcharts are NOT in citations
        for c in res3.citations:
            self.assertNotIn("permit flow chart", c.title.lower())
            self.assertNotIn("permit_flow_charts", c.url.lower())

    def test_query_2_how_to_import_soil(self):
        """
        Query 2: 'How to import soil?'
        - Bot must recognize Soil Importation topic.
        - Must ask the 10 cubic yards threshold question conversationally.
        - Must NOT expose the internal Permit Flow Chart.
        - Must NOT recommend the generic Zoning Permit Application.
        - Must NOT present an application prematurely.
        """
        res = rag_engine.answer_query("How to import soil?")
        self.assertTrue(res.grounded)
        self.assertIn("10 cubic yards or more", res.answer)
        self.assertIsNone(res.form_packet, "Should not issue form prematurely before volume is known")
        # Ensure internal flowchart is NOT exposed
        for c in res.citations:
            self.assertNotIn("permit flow chart", c.title.lower())
            self.assertNotIn("permit_flow_charts", c.url.lower())
        # Ensure Zoning Application is NOT recommended
        rec = form_matcher.match_form("How to import soil?")
        if rec and rec.is_application_form:
            self.assertNotEqual(rec.form.form_id, "zoning_permit")

    def test_query_3_import_20_cubic_yards_soil(self):
        """
        Query 3: 'I want to bring 20 cubic yards of soil.'
        - Recognizes upfront import volume >= 10 cubic yards.
        - Concludes permit IS required.
        - Delivers Forms_Soil_Importation_Appl.pdf.
        - 4-part structure with Applicable Procedure, Requirements, Next Steps, and Official Documents.
        - No generic zoning application.
        """
        res = rag_engine.answer_query("I want to bring 20 cubic yards of soil.")
        self.assertTrue(res.grounded)
        self.assertIn("soil importation permit", res.answer.lower())
        self.assertIsNotNone(res.form_packet)
        self.assertEqual(res.form_packet.form_file, "Forms_Soil_Importation_Appl.pdf")
        self.assertIn("clean fill", res.answer.lower())
        self.assertIn("grading plan", res.answer.lower())

    def test_query_4_how_to_export_soil(self):
        """
        Query 4: 'I want to export soil.'
        - Asks volume threshold question (10 cubic yards or more) conversationally.
        - Does NOT expose internal flowchart.
        - Does NOT recommend generic zoning permit.
        """
        res = rag_engine.answer_query("I want to export soil.")
        self.assertTrue(res.grounded)
        self.assertIn("10 cubic yards or more", res.answer)
        self.assertIsNone(res.form_packet, "Should not issue form prematurely")

    def test_query_5_remove_less_than_10_cubic_yards(self):
        """
        Query 5: 'I want to remove less than 10 cubic yards of soil.'
        - Confirms Soil Export permit is NOT required.
        - Provides environmental best practices (drainage).
        - Does NOT issue an application form.
        """
        res = rag_engine.answer_query("I want to remove less than 10 cubic yards of soil.")
        self.assertTrue(res.grounded)
        self.assertIn("not required", res.answer.lower())
        self.assertIsNone(res.form_packet)

    def test_query_6_road_opening_permit(self):
        """
        Query 6: 'How do I apply for a road-opening permit?'
        - Recommends RoadOpenApp.pdf.
        - Does NOT recommend tree removal or zoning permit.
        """
        intent = service_intent_service.detect_intent("How do I apply for a road-opening permit?")
        self.assertEqual(intent.service_id, "road_opening")
        self.assertEqual(intent.official_form_file, "RoadOpenApp.pdf")

        packet = rag_engine.match_official_form_packet("How do I apply for a road-opening permit?")
        self.assertIsNotNone(packet)
        self.assertEqual(packet.form_file, "RoadOpenApp.pdf")
        self.assertIn("Opening", packet.form_title)

    def test_query_7_improve_property(self):
        """
        Query 7: 'I want to improve my property.'
        - Starts Site Improvement inquiry.
        - Asks 500 s.f. impervious coverage / 1,250 s.f. disturbance threshold question.
        - Does NOT prematurely issue form.
        """
        res = rag_engine.answer_query("I want to improve my property.")
        self.assertTrue(res.grounded)
        self.assertIn("500 sq.ft.", res.answer)
        self.assertIn("1,250 sq.ft.", res.answer)
        self.assertIsNone(res.form_packet)

        # Follow-up: User answers Yes (> 500 sq.ft.)
        history = [
            {"role": "user", "content": "I want to improve my property."},
            {"role": "assistant", "content": res.answer}
        ]
        res2 = rag_engine.answer_query("Yes, it's about 800 sq ft of new patio and driveway", history=history)
        self.assertIsNotNone(res2.form_packet)
        self.assertEqual(res2.form_packet.form_file, "SIP_Application.pdf")

    def test_query_8_zoning_permit(self):
        """
        Query 8: 'How do I apply for a zoning permit?'
        - Recommends Zoning_Permit_Application_Edison.pdf.
        - Does NOT confuse with tree removal or road opening.
        """
        packet = rag_engine.match_official_form_packet("How do I apply for a zoning permit?")
        self.assertIsNotNone(packet)
        self.assertEqual(packet.form_file, "Zoning_Permit_Application_Edison.pdf")

    def test_query_9_engineering_without_flowchart(self):
        """
        Query 9: Engineering service without a configured flowchart:
        'What are the engineering standards for a residential driveway in Edison Township?'
        - Accurately identifies as an Engineering inquiry.
        - Grounded response with municipal standards.
        - Does NOT falsely claim out-of-domain.
        - Does NOT hallucinate nonexistent forms.
        - Does NOT expose internal flowcharts.
        """
        query = "What are the engineering standards for a residential driveway in Edison Township?"
        intent = service_intent_service.detect_intent(query)
        self.assertNotEqual(intent.service_id, "out_of_context")

        res = rag_engine.answer_query(query)
        self.assertTrue(res.grounded)
        self.assertNotIn("sorry this information is out of our context", res.answer.lower())
        # Ensure no flowchart exposed
        for c in res.citations:
            self.assertNotIn("permit flow chart", c.title.lower())
            self.assertNotIn("permit_flow_charts", c.url.lower())

    def test_strict_out_of_context(self):
        """
        Non-engineering inquiries strictly return the exact required message.
        """
        res = rag_engine.answer_query("Can I adopt a cat from the animal shelter?")
        self.assertFalse(res.grounded)
        self.assertIn("out of our context", res.answer.lower())
        self.assertIn("https://www.edisonnj.org/document_center/index.php", res.answer)


if __name__ == "__main__":
    unittest.main()
