"""User management service."""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import User, Race


class UserService:
    """Service for managing user data and operations."""
    
    @staticmethod
    async def get_user_by_discord_id(session: AsyncSession, discord_id: int) -> Optional[User]:
        """Get a user by Discord ID."""
        result = await session.execute(
            select(User).where(User.discord_id == discord_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(session: AsyncSession, discord_id: int) -> User:
        """Create a new user with default values."""
        user = User(
            discord_id=discord_id,
            terms_accepted=False,
            setup_completed=False,
        )
        session.add(user)
        await session.flush()
        return user
    
    @staticmethod
    async def accept_terms_of_service(session: AsyncSession, discord_id: int) -> User:
        """Mark that a user has accepted the Terms of Service."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        
        if not user:
            user = await UserService.create_user(session, discord_id)
        
        user.terms_accepted = True
        user.terms_accepted_at = datetime.utcnow()
        await session.flush()
        return user
    
    @staticmethod
    async def has_accepted_terms(session: AsyncSession, discord_id: int) -> bool:
        """Check if a user has accepted the Terms of Service."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        return user is not None and user.terms_accepted
    
    @staticmethod
    async def has_completed_setup(session: AsyncSession, discord_id: int) -> bool:
        """Check if a user has completed setup."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        return user is not None and user.setup_completed
    
    @staticmethod
    async def update_user_setup(
        session: AsyncSession,
        discord_id: int,
        main_id: str,
        alt_ids: List[str],
        battle_tag: str,
        country_code: str,
        region_code: str
    ) -> User:
        """Update user information from setup."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        
        if not user:
            raise ValueError(f"User with Discord ID {discord_id} not found")
        
        user.main_id = main_id
        user.alt_ids = alt_ids
        user.battle_tag = battle_tag
        user.country_code = country_code
        user.region_code = region_code
        user.setup_completed = True
        user.setup_completed_at = datetime.utcnow()
        
        await session.flush()
        return user
    
    @staticmethod
    async def update_country(
        session: AsyncSession,
        discord_id: int,
        country_code: str
    ) -> User:
        """Update just the user's country."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        
        if not user:
            raise ValueError(f"User with Discord ID {discord_id} not found")
        
        user.country_code = country_code
        await session.flush()
        return user
    
    @staticmethod
    async def get_user_mmr(session: AsyncSession, discord_id: int) -> Dict[str, float]:
        """Get all MMR values for a user."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        
        if not user:
            raise ValueError(f"User with Discord ID {discord_id} not found")
        
        return {
            "bw_terran": user.mmr_bw_terran,
            "bw_zerg": user.mmr_bw_zerg,
            "bw_protoss": user.mmr_bw_protoss,
            "sc2_terran": user.mmr_sc2_terran,
            "sc2_zerg": user.mmr_sc2_zerg,
            "sc2_protoss": user.mmr_sc2_protoss,
        }
    
    @staticmethod
    async def update_user_stats(
        session: AsyncSession,
        user_id: int,
        win: bool = False,
        loss: bool = False,
        draw: bool = False
    ) -> User:
        """Update user win/loss/draw statistics."""
        user = await session.get(User, user_id)
        
        if not user:
            raise ValueError(f"User with ID {user_id} not found")
        
        if win:
            user.wins_1v1 += 1
        elif loss:
            user.losses_1v1 += 1
        elif draw:
            user.draws_1v1 += 1
        
        user.last_active_at = datetime.utcnow()
        await session.flush()
        return user
    
    @staticmethod
    async def update_user_preferences(
        session: AsyncSession,
        discord_id: int,
        map_vetoes: Optional[List[str]] = None,
        last_queue_races: Optional[List[str]] = None
    ) -> User:
        """Update user preferences like map vetoes and last queued races."""
        user = await UserService.get_user_by_discord_id(session, discord_id)
        
        if not user:
            raise ValueError(f"User with Discord ID {discord_id} not found")
        
        if map_vetoes is not None:
            user.map_vetoes = map_vetoes
        
        if last_queue_races is not None:
            user.last_queue_races = last_queue_races
        
        await session.flush()
        return user
    
    @staticmethod
    async def reset_all_mmr(session: AsyncSession):
        """Reset all user MMRs to initial value (admin function)."""
        await session.execute(
            update(User).values(
                mmr_bw_terran=1500.0,
                mmr_bw_zerg=1500.0,
                mmr_bw_protoss=1500.0,
                mmr_sc2_terran=1500.0,
                mmr_sc2_zerg=1500.0,
                mmr_sc2_protoss=1500.0,
                wins_1v1=0,
                losses_1v1=0,
                draws_1v1=0,
            )
        )
        await session.flush()
