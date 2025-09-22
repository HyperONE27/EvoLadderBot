"""
MMR service. Uses an ELO rating system.

This module defines the MMRService class, which contains methods for:
- Updating player MMRs after a match
- Applying MMR decay
- Performing manual adjustments for administrative purposes

Intended usage:
    from backend.services.mmr_service import MMRService

    mmr = MMRService()
    mmr.update_mmr(player_id, new_mmr)
    mmr.apply_mmr_decay(player_id)
    mmr.perform_manual_adjustment(player_id, adjustment)
"""