"""
Comprehensive Regression Test Suite for Tree Removal Decision Flow & Road Opening Isolation
Official Reference: Township of Edison Permit Flow Charts (Page 3: Tree Removal Permit)
https://cms2.revize.com/revize/edisonnj/document_center/Permit%20Flow%20Charts.pdf
"""

import unittest
from backend.app.main import chat_endpoint
from backend.app.models.core import ChatRequest
from backend.app.flow_engine import flow_engine
from backend.app.services.form_matcher import form_matcher


class TestTreeRemovalRegression(unittest.TestCase):
    def setUp(self):
        # Clear engine sessions between tests
        flow_engine.sessions.clear()

    # --------------------------------------------------------------------------
    # Test 1: "Help me with tree removal procedure."
    # --------------------------------------------------------------------------
    def test_01_tree_removal_procedure_initial_inquiry(self):
        """Initial tree removal procedure query must start Step 1, never return Road Opening."""
        sid = "reg_test_01"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Help me with tree removal procedure",
            department_id="engineering"
        ))

        self.assertEqual(res.mode, "flow")
        self.assertEqual(res.active_flow_id, "tree_removal_flow")
        self.assertFalse(res.completed)
        self.assertIsNotNone(res.current_step)
        self.assertEqual(res.current_step.id, "step_removing_trees_check")
        
        # Must ask Question A: planning to remove one or more trees
        self.assertIn("planning to remove one or more trees", res.message.lower())
        self.assertEqual(len(res.options), 2)
        self.assertEqual(res.options[0].id, "opt_removing_trees_yes")
        self.assertEqual(res.options[1].id, "opt_removing_trees_no")

        # CRITICAL BUG VERIFICATION: Form packet must NOT be Road Opening or any fake form
        self.assertIsNone(res.form_packet)
        self.assertNotIn("road opening", res.message.lower())
        self.assertNotIn("roadopenapp", res.message.lower())
        self.assertNotIn("excavation", res.message.lower())

        # Citations must reference Permit Flow Charts
        self.assertTrue(len(res.citations) > 0)
        self.assertIn("Permit%20Flow%20Charts.pdf", res.citations[0].url)

    # --------------------------------------------------------------------------
    # Test 2: Multi-turn: Step 1 (Yes) -> Step 2 (Yes, Emergency)
    # --------------------------------------------------------------------------
    def test_02_multiturn_emergency_protocol(self):
        """Step 1 (Yes) -> Step 2 (Emergency Yes) -> Emergency Protocol Result."""
        sid = "reg_test_02"
        # Turn 1
        r1 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Help me with tree removal procedure",
            department_id="engineering"
        ))
        self.assertEqual(r1.current_step.id, "step_removing_trees_check")

        # Turn 2: Resident answers YES to removing trees
        r2 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Yes, I am removing a tree",
            department_id="engineering"
        ))
        self.assertEqual(r2.current_step.id, "step_emergency_check")
        self.assertIn("emergency situation where the tree is dead, dying, or poses an immediate danger", r2.message.lower())
        self.assertIsNone(r2.form_packet)

        # Turn 3: Resident answers YES to emergency
        r3 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Yes, it is dead and leaning dangerously over the driveway",
            department_id="engineering"
        ))
        self.assertTrue(r3.completed)
        self.assertEqual(r3.current_step.id, "step_emergency_protocol_result")
        
        # Verify official Page 3 emergency requirements
        msg = r3.message.lower()
        self.assertIn("photographic proof", msg)
        self.assertIn("licensed arborist", msg)
        self.assertIn("concurrent", msg)
        self.assertIn("remove the tree immediately", msg)
        
        # Form verification status statement
        self.assertIn("standalone", msg)
        self.assertIn("not yet been verified", msg)
        self.assertIn("https://www.edisonnj.org/document_center/index.php", msg)

        # No form packet attached (no fake form, no road opening)
        self.assertIsNone(r3.form_packet)

    # --------------------------------------------------------------------------
    # Test 3: Multi-turn: Step 1 (Yes) -> Step 2 (No, Planned/Healthy)
    # --------------------------------------------------------------------------
    def test_03_multiturn_planned_permit_required(self):
        """Step 1 (Yes) -> Step 2 (Emergency No) -> Tree Removal Permit Required."""
        sid = "reg_test_03"
        chat_endpoint(ChatRequest(session_id=sid, message="Help me with tree removal procedure"))
        chat_endpoint(ChatRequest(session_id=sid, message="Yes, I want to remove trees"))
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="No, it is a healthy tree for landscape redesign"))

        self.assertTrue(r3.completed)
        self.assertEqual(r3.current_step.id, "step_planned_permit_required_result")
        self.assertIn("tree removal permit is required", r3.message.lower())
        self.assertIn("not yet been verified", r3.message.lower())
        self.assertIsNone(r3.form_packet)

    # --------------------------------------------------------------------------
    # Test 4: Multi-turn: Step 1 (No trees) -> Step 2B (Not subdivision) -> NOT required
    # --------------------------------------------------------------------------
    def test_04_multiturn_no_trees_not_subdivision(self):
        """Step 1 (No trees) -> Step 2B (Not subdivision/demolition) -> Permit NOT required."""
        sid = "reg_test_04"
        chat_endpoint(ChatRequest(session_id=sid, message="Help me with tree removal procedure"))
        
        # Turn 2: No trees being removed
        r2 = chat_endpoint(ChatRequest(session_id=sid, message="No, I am not removing any trees"))
        self.assertEqual(r2.current_step.id, "step_subdivision_demolition_check")
        self.assertIn("part of a subdivision or does it require a demolition permit", r2.message.lower())

        # Turn 3: Not part of subdivision
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="No, neither"))
        self.assertTrue(r3.completed)
        self.assertEqual(r3.current_step.id, "step_permit_not_required_result")
        self.assertIn("tree removal permit is not required", r3.message.lower())
        self.assertIsNone(r3.form_packet)

    # --------------------------------------------------------------------------
    # Test 5: Multi-turn: Step 1 (No trees) -> Step 2B (Subdivision) -> REQUIRED
    # --------------------------------------------------------------------------
    def test_05_multiturn_no_trees_subdivision_permit_required(self):
        """Step 1 (No trees) -> Step 2B (Subdivision YES) -> Tree Removal Permit REQUIRED."""
        sid = "reg_test_05"
        chat_endpoint(ChatRequest(session_id=sid, message="Help me with tree removal procedure"))
        chat_endpoint(ChatRequest(session_id=sid, message="No trees are being removed"))
        r3 = chat_endpoint(ChatRequest(session_id=sid, message="Yes, the project is part of a subdivision"))

        self.assertTrue(r3.completed)
        self.assertEqual(r3.current_step.id, "step_subdivision_permit_required_result")
        self.assertIn("tree removal permit is required", r3.message.lower())
        self.assertIsNone(r3.form_packet)

    # --------------------------------------------------------------------------
    # Test 6: Upfront Query: "I want to remove a dead tree."
    # --------------------------------------------------------------------------
    def test_06_upfront_dead_tree_short_circuit(self):
        """Resident explicitly states 'dead tree' upfront -> immediate emergency protocol."""
        sid = "reg_test_06"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I want to remove a dead tree.",
            department_id="engineering"
        ))
        self.assertTrue(res.completed)
        self.assertEqual(res.current_step.id, "step_emergency_protocol_result")
        self.assertIn("photographic proof", res.message.lower())
        self.assertIn("concurrent", res.message.lower())
        self.assertIsNone(res.form_packet)
        self.assertNotIn("road opening", res.message.lower())

    # --------------------------------------------------------------------------
    # Test 7: Upfront Query: "A tree is falling and poses an immediate danger."
    # --------------------------------------------------------------------------
    def test_07_upfront_falling_tree_immediate_danger(self):
        """Resident states 'falling and poses an immediate danger' -> emergency protocol."""
        sid = "reg_test_07"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="A tree is falling and poses an immediate danger.",
            department_id="engineering"
        ))
        self.assertTrue(res.completed)
        self.assertEqual(res.current_step.id, "step_emergency_protocol_result")
        self.assertIn("remove the tree immediately", res.message.lower())
        self.assertIsNone(res.form_packet)

    # --------------------------------------------------------------------------
    # Test 8: Upfront Query: "I want to remove a healthy tree."
    # --------------------------------------------------------------------------
    def test_08_upfront_healthy_tree(self):
        """Resident states 'healthy tree' upfront -> permit required."""
        sid = "reg_test_08"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I want to remove a healthy tree.",
            department_id="engineering"
        ))
        self.assertTrue(res.completed)
        self.assertEqual(res.current_step.id, "step_planned_permit_required_result")
        self.assertIn("tree removal permit is required", res.message.lower())
        self.assertIsNone(res.form_packet)

    # --------------------------------------------------------------------------
    # Test 9: Upfront Query: "I am not removing any trees."
    # --------------------------------------------------------------------------
    def test_09_upfront_not_removing_trees(self):
        """Resident states 'not removing any trees' upfront -> asks subdivision/demolition check."""
        sid = "reg_test_09"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I am not removing any trees.",
            department_id="engineering"
        ))
        self.assertFalse(res.completed)
        self.assertEqual(res.current_step.id, "step_subdivision_demolition_check")
        self.assertIn("part of a subdivision or does it require a demolition permit", res.message.lower())

    # --------------------------------------------------------------------------
    # Test 10: Upfront Query: "My project is part of a subdivision."
    # --------------------------------------------------------------------------
    def test_10_upfront_subdivision(self):
        """Resident states 'My project is part of a subdivision.' -> subdivision permit required."""
        sid = "reg_test_10"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="My project is part of a subdivision.",
            department_id="engineering"
        ))
        self.assertTrue(res.completed)
        self.assertEqual(res.current_step.id, "step_subdivision_permit_required_result")
        self.assertIn("tree removal permit is required", res.message.lower())
        self.assertIsNone(res.form_packet)

    # --------------------------------------------------------------------------
    # Test 11: "I need a road-opening permit." -> Strictly Road Opening, No Tree Removal
    # --------------------------------------------------------------------------
    def test_11_road_opening_no_tree_bleeding(self):
        """Road-opening query must NEVER mention tree removal or tree flowchart."""
        sid = "reg_test_11"
        res = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I need a road-opening permit.",
            department_id="engineering"
        ))
        self.assertEqual(res.active_flow_id, "street_opening_flow")
        self.assertNotIn("tree removal", res.message.lower())
        self.assertNotIn("arborist", res.message.lower())
        self.assertNotIn("step_removing_trees_check", str(res))

    # --------------------------------------------------------------------------
    # Test 12: Multi-turn Context Bleed: Road Opening followed by Tree Removal
    # --------------------------------------------------------------------------
    def test_12_cross_topic_history_isolation(self):
        """
        After discussing road opening, resident asks 'Help me with tree removal procedure'.
        The response MUST NOT return RoadOpenApp.pdf or road opening guidance.
        """
        sid = "reg_test_12_bleed"
        
        # Turn 1: Discuss Road Opening
        r1 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="I need to dig in the street for utility connection and need the road opening application form.",
            department_id="engineering"
        ))
        self.assertIsNotNone(r1.form_packet)
        self.assertEqual(r1.form_packet.form_code, "EDISON-DPW-ROADOPEN")

        # Turn 2: Switch to Tree Removal
        r2 = chat_endpoint(ChatRequest(
            session_id=sid,
            message="Help me with tree removal procedure",
            department_id="engineering"
        ))
        
        # Must start tree removal flow
        self.assertEqual(r2.active_flow_id, "tree_removal_flow")
        self.assertEqual(r2.current_step.id, "step_removing_trees_check")
        self.assertIn("planning to remove one or more trees", r2.message.lower())

        # Must NOT carry over Road Opening form packet!
        self.assertIsNone(r2.form_packet)
        self.assertNotIn("road opening", r2.message.lower())
        self.assertNotIn("roadopenapp", r2.message.lower())


if __name__ == "__main__":
    unittest.main()
