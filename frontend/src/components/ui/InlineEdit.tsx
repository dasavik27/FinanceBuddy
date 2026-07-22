import React, { useState, useEffect, useRef } from 'react';
import { Box, Typography, InputBase } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';

export const InlineEdit = ({ 
  value, 
  onSave, 
  placeholder = '', 
  type = 'text', 
  formatDisplay = (v: any) => v,
  textProps = {},
  inputProps = {},
  sx = {}
}: any) => {
  const [isEditing, setIsEditing] = useState(false);
  const [currentValue, setCurrentValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setCurrentValue(value);
  }, [value]);

  const handleSave = () => {
    setIsEditing(false);
    if (currentValue !== value) {
      onSave(type === 'number' ? Number(currentValue) : currentValue);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    } else if (e.key === 'Escape') {
      setIsEditing(false);
      setCurrentValue(value);
    }
  };

  if (isEditing) {
    return (
      <InputBase
        inputRef={inputRef}
        autoFocus
        size="small"
        placeholder={placeholder}
        value={currentValue}
        onChange={(e) => setCurrentValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        type={type}
        sx={{ 
          bgcolor: 'rgba(255,255,255,0.08)',
          borderRadius: '6px',
          px: 1,
          py: 0.2,
          color: '#fff',
          border: '1px solid rgba(129, 140, 248, 0.5)',
          boxShadow: '0 0 0 2px rgba(129, 140, 248, 0.2)',
          transition: 'all 0.2s',
          input: { 
            p: 0,
            ...inputProps
          }, 
          ...sx 
        }}
      />
    );
  }

  return (
    <Box 
      onClick={() => setIsEditing(true)}
      sx={{ 
        display: 'inline-flex', 
        alignItems: 'center', 
        gap: 0.75, 
        cursor: 'pointer',
        px: 1,
        py: 0.25,
        borderRadius: '6px',
        border: '1px dashed rgba(255,255,255,0.25)',
        bgcolor: 'rgba(255,255,255,0.02)',
        transition: 'all 0.2s',
        '&:hover': {
          bgcolor: 'rgba(255,255,255,0.08)',
          borderColor: 'rgba(255,255,255,0.5)',
          '& .edit-icon': { opacity: 1, color: '#818CF8' }
        },
        ...sx
      }}
    >
      <Typography {...textProps}>
        {formatDisplay(currentValue)}
      </Typography>
      <EditIcon 
        className="edit-icon" 
        sx={{ 
          fontSize: 14, 
          color: 'rgba(255,255,255,0.4)', 
          opacity: 0.6,
          transition: 'all 0.2s'
        }} 
      />
    </Box>
  );
}
