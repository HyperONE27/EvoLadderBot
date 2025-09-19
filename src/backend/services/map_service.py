"""Map pool management service."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.models import MapPool


class MapService:
    """Service for managing the map pool."""
    
    @staticmethod
    async def get_active_maps(session: AsyncSession) -> List[MapPool]:
        """Get all active maps in the pool."""
        result = await session.execute(
            select(MapPool)
            .where(MapPool.is_active == True)
            .order_by(MapPool.order_index)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_map_names(session: AsyncSession) -> List[str]:
        """Get names of all active maps."""
        maps = await MapService.get_active_maps(session)
        return [m.map_name for m in maps]
    
    @staticmethod
    async def update_map_pool(session: AsyncSession, new_maps: List[str]) -> List[MapPool]:
        """Update the entire map pool (admin function)."""
        # Mark all current maps as inactive
        await session.execute(
            update(MapPool)
            .where(MapPool.is_active == True)
            .values(
                is_active=False,
                removed_at=datetime.utcnow()
            )
        )
        
        # Add new maps
        new_map_entries = []
        for idx, map_name in enumerate(new_maps):
            # Check if map already exists
            result = await session.execute(
                select(MapPool).where(MapPool.map_name == map_name)
            )
            existing_map = result.scalar_one_or_none()
            
            if existing_map:
                # Reactivate existing map
                existing_map.is_active = True
                existing_map.removed_at = None
                existing_map.order_index = idx
                new_map_entries.append(existing_map)
            else:
                # Create new map
                new_map = MapPool(
                    map_name=map_name,
                    is_active=True,
                    order_index=idx
                )
                session.add(new_map)
                new_map_entries.append(new_map)
        
        await session.flush()
        return new_map_entries
    
    @staticmethod
    async def add_map(session: AsyncSession, map_name: str) -> MapPool:
        """Add a single map to the pool."""
        # Check if map already exists
        result = await session.execute(
            select(MapPool).where(MapPool.map_name == map_name)
        )
        existing_map = result.scalar_one_or_none()
        
        if existing_map:
            if existing_map.is_active:
                raise ValueError(f"Map '{map_name}' is already in the active pool")
            
            # Reactivate existing map
            existing_map.is_active = True
            existing_map.removed_at = None
            await session.flush()
            return existing_map
        
        # Get max order index
        result = await session.execute(
            select(MapPool.order_index)
            .where(MapPool.is_active == True)
            .order_by(MapPool.order_index.desc())
            .limit(1)
        )
        max_index = result.scalar_one_or_none() or -1
        
        # Create new map
        new_map = MapPool(
            map_name=map_name,
            is_active=True,
            order_index=max_index + 1
        )
        session.add(new_map)
        await session.flush()
        return new_map
    
    @staticmethod
    async def remove_map(session: AsyncSession, map_name: str) -> bool:
        """Remove a map from the active pool."""
        result = await session.execute(
            select(MapPool).where(
                MapPool.map_name == map_name,
                MapPool.is_active == True
            )
        )
        map_entry = result.scalar_one_or_none()
        
        if not map_entry:
            return False
        
        map_entry.is_active = False
        map_entry.removed_at = datetime.utcnow()
        await session.flush()
        return True
